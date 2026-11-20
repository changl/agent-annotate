"""The prototype's machine-load reader parses sysctl output and the recorder's tail the same way on every Mac."""

import time

from agent_annotate.proto_data.running import load_entry


def test_load_entry_reads_sysctl_and_the_last_day():
    now = int(time.time())
    tsv = "\n".join(["cut-in-half", f"{now - 90000}\t9\t9\t9\t1\t1\t50%\t1",
                     f"{now - 60}\t4.5\t4\t3\t262144\t10\t69%\t600"])
    e = load_entry("{ 4.50 4.00 3.00 } 18 17179869184 16384", tsv)
    assert e["load"] == [4.5, 4.0, 3.0] and e["cpus"] == 18
    assert e["hist"] == [[now - 60, 4.5, 25.0, 69]] and e["recorded"] and e["since"] == now - 60


def test_load_entry_without_readings_is_not_recorded():
    assert load_entry("{ 1 2 3 } 8 8589934592 16384", "")["recorded"] is False
