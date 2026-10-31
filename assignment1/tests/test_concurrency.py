import threading
from collections import Counter
from decimal import Decimal

from conftest import outstanding, payment_count

from ledger import DUPLICATE, POSTED, connect, post_payment

THREADS = 8


def _race(db_path, txn_ids):
    """Start len(txn_ids) threads at the same instant, each with its own connection."""
    barrier = threading.Barrier(len(txn_ids))
    results, errors = [], []
    lock = threading.Lock()

    def worker(txn_id):
        c = connect(db_path)          # sqlite3 connections must not be shared across threads
        try:
            barrier.wait()
            r = post_payment(c, "L1", Decimal("1000.00"), txn_id)
            with lock:
                results.append(r)
        except Exception as e:        # surface errors to the main thread instead of losing them
            with lock:
                errors.append(e)
        finally:
            c.close()

    threads = [threading.Thread(target=worker, args=(t,)) for t in txn_ids]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)
    return results, errors


def test_eight_threads_same_txn_exactly_one_succeeds(conn, db_path):
    results, errors = _race(db_path, ["TXN-RACE"] * THREADS)

    assert errors == []
    assert Counter(results) == {POSTED: 1, DUPLICATE: THREADS - 1}
    assert payment_count(conn) == 1
    assert outstanding(conn, "L1") == 1000000 - 100000


def test_eight_threads_distinct_txns_all_apply(conn, db_path):
    """Control: the lock must not swallow legitimate concurrent payments (no lost updates)."""
    results, errors = _race(db_path, [f"TXN-{i}" for i in range(THREADS)])

    assert errors == []
    assert Counter(results) == {POSTED: THREADS}
    assert outstanding(conn, "L1") == 1000000 - THREADS * 100000
