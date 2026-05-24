"""Tareas 6 y 7: orquestador de umbral M-de-N — junta M, fail-closed con menos, nodo malicioso."""

from unittest.mock import MagicMock

import pytest

pytest.importorskip("safe_eth")

from eth_account import Account  # noqa: E402

from aval.execution.cosigner_client import CosignerUnavailable  # noqa: E402
from aval.execution.models import AuthorizationResponse  # noqa: E402
from aval.execution.safe_tx import signer_of  # noqa: E402
from aval.execution.signer import RawKeySigner  # noqa: E402
from aval.execution.transfer_executor import SafeTransferExecutor, TokenSpec  # noqa: E402
from aval.models import Decision  # noqa: E402

SAFE = "0x" + "11" * 20
ALICE = "0x" + "33" * 20
CHAIN = 11155111


class FakeCosigner:
    """Co-autorizador en memoria: firma con su propia llave si autoriza."""

    def __init__(self, allow: bool = True) -> None:
        self.signer = RawKeySigner(Account.create().key.hex())
        self._allow = allow
        self.reported = 0

    def authorize(self, req) -> AuthorizationResponse:  # type: ignore[no-untyped-def]
        if self._allow:
            sig = self.signer.sign_hash(req.safe_tx_hash)
            return AuthorizationResponse(decision=Decision.allow(), aval_signature=sig)
        return AuthorizationResponse(
            decision=Decision.deny("fuera del mandato"), aval_signature=None
        )

    def report_execution(self, report) -> None:  # type: ignore[no-untyped-def]
        self.reported += 1


class DownCosigner:
    def authorize(self, req):  # type: ignore[no-untyped-def]
        raise CosignerUnavailable("caído")

    def report_execution(self, report) -> None:  # type: ignore[no-untyped-def]
        pass


def _chain() -> MagicMock:
    chain = MagicMock()
    chain.get_nonce.return_value = 0
    chain.exec_transaction.return_value = "0x" + "ab" * 32
    return chain


def _executor(cosigners: list, threshold_m: int, chain: MagicMock) -> SafeTransferExecutor:
    return SafeTransferExecutor(
        safe_address=SAFE,
        chain_id=CHAIN,
        agent_private_key=Account.create().key.hex(),
        chain=chain,
        cosigners=cosigners,
        threshold_m=threshold_m,
        tokens={"ETH": TokenSpec(None, 18)},
    )


def test_gathers_m_signatures_and_executes() -> None:
    chain = _chain()
    cosigners = [FakeCosigner(allow=True) for _ in range(3)]
    out = _executor(cosigners, threshold_m=2, chain=chain).transfer(ALICE, "1", "ETH")
    assert out["executed"] is True
    chain.exec_transaction.assert_called_once()
    # firmas combinadas = agente + 2 aval = 3 × 65 bytes
    _req, combined, _key = chain.exec_transaction.call_args.args
    assert len(bytes.fromhex(combined[2:])) == 3 * 65


def test_fails_closed_with_fewer_than_m() -> None:
    chain = _chain()
    # umbral 2, pero solo 1 autoriza (2 deniegan)
    cosigners = [FakeCosigner(allow=True), FakeCosigner(allow=False), FakeCosigner(allow=False)]
    out = _executor(cosigners, threshold_m=2, chain=chain).transfer(ALICE, "1", "ETH")
    assert out["executed"] is False
    assert "insuficientes" in out["reason"]
    chain.exec_transaction.assert_not_called()


def test_tolerates_down_node_if_m_available() -> None:
    chain = _chain()
    cosigners = [DownCosigner(), FakeCosigner(allow=True), FakeCosigner(allow=True)]
    out = _executor(cosigners, threshold_m=2, chain=chain).transfer(ALICE, "1", "ETH")
    assert out["executed"] is True  # quedaban 2 disponibles
    chain.exec_transaction.assert_called_once()


def test_single_malicious_node_cannot_reach_threshold() -> None:
    chain = _chain()
    # 1 nodo malicioso (autoriza todo) + 2 honestos que deniegan una acción fuera del mandato
    malicious = FakeCosigner(allow=True)
    honest1 = FakeCosigner(allow=False)
    honest2 = FakeCosigner(allow=False)
    out = _executor([malicious, honest1, honest2], threshold_m=2, chain=chain).transfer(
        ALICE, "1", "ETH"
    )
    assert out["executed"] is False  # 1 firma maliciosa < umbral 2
    chain.exec_transaction.assert_not_called()


def test_combined_signatures_recover_to_distinct_signers() -> None:
    chain = _chain()
    cosigners = [FakeCosigner(allow=True) for _ in range(2)]
    _executor(cosigners, threshold_m=2, chain=chain).transfer(ALICE, "1", "ETH")
    req, combined, _ = chain.exec_transaction.call_args.args
    # las 3 firmas (agente + 2 aval) recuperan a 3 direcciones distintas
    sigs = [combined[2:][i * 130 : (i + 1) * 130] for i in range(3)]
    addrs = {signer_of(req.safe_tx_hash, "0x" + s).lower() for s in sigs}
    assert len(addrs) == 3
