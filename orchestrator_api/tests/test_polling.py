"""poll_until : issue dès qu'elle existe, None au délai, exception transmise telle quelle."""
import pytest

from app.core.polling import poll_until


@pytest.mark.anyio
async def test_renvoie_la_premiere_issue_non_nulle():
    outcomes = iter([None, None, "SUCCESS"])

    async def probe():
        return next(outcomes)

    assert await poll_until(probe, timeout=1, interval=0.01) == "SUCCESS"


@pytest.mark.anyio
async def test_false_est_une_issue_terminale():
    async def probe():
        return False

    assert await poll_until(probe, timeout=1, interval=0.01) is False


@pytest.mark.anyio
async def test_none_au_dela_du_delai():
    calls = 0

    async def probe():
        nonlocal calls
        calls += 1
        return None

    assert await poll_until(probe, timeout=0.05, interval=0.01) is None
    assert calls > 1


@pytest.mark.anyio
async def test_une_exception_remonte_sans_attendre():
    async def probe():
        raise ConnectionError("injoignable")

    with pytest.raises(ConnectionError):
        await poll_until(probe, timeout=5, interval=0.01)
