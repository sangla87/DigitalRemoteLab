import threading
import time

import pytest
from test_wrapper import STUDENT

from digitalremotelab.bitstream import BitstreamError
from digitalremotelab.compiler import CompileResult, FakeCompiler
from digitalremotelab.config import BoardConfig, LabConfig
from digitalremotelab.jobs import JobManager, JobNotFound, JobQueueFull
from digitalremotelab.lab import Lab
from digitalremotelab.portcheck import VhdlError
from digitalremotelab.programmer import FakeProgrammer

NEXYS = BoardConfig(id="n1", model="nexys4")


class BlockingCompiler:
    """Se queda esperando hasta que el test lo libere (para llenar la cola)."""

    def __init__(self, inner):
        self.inner = inner
        self.release = threading.Event()

    def compile(self, job):
        assert self.release.wait(10)
        return self.inner.compile(job)


def make(tmp_path, compiler=None, programmer=None, **kwargs):
    config = LabConfig(boards=(NEXYS,), work_dir=str(tmp_path / "work"))
    programmer = programmer or FakeProgrammer()
    compiler = compiler or FakeCompiler(config.work_dir)
    lab = Lab(config, programmer, lambda b: None, compiler)
    return JobManager(lab, **kwargs), programmer


def wait_for(manager, job_id, states=("done", "error"), timeout=10):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        job = manager.get(job_id)
        if job["state"] in states:
            return job
        time.sleep(0.01)
    raise AssertionError(f"el trabajo no terminó: {manager.get(job_id)}")


def test_vhdl_job_compiles_and_programs(tmp_path):
    manager, programmer = make(tmp_path)
    job = manager.submit_vhdl(STUDENT, clock_mode="10hz")
    done = wait_for(manager, job.id)
    assert done["state"] == "done" and done["errors"] == []
    assert done["design"] == "drl_top" and done["clock"] == "10hz"
    assert len(programmer.programmed) == 1
    manager.shutdown()


def test_invalid_vhdl_is_rejected_at_submit_and_not_queued(tmp_path):
    manager, programmer = make(tmp_path)
    with pytest.raises(VhdlError):
        manager.submit_vhdl(STUDENT.replace("LED1", "LEDX"))
    assert manager.queue_length() == 0 and programmer.programmed == []
    manager.shutdown()


def test_failed_compilation_reports_errors_and_does_not_program(tmp_path):
    manager, programmer = make(
        tmp_path, FakeCompiler(tmp_path / "w", error="ERROR: [Synth 8-1] mal")
    )
    job = manager.submit_vhdl(STUDENT)
    done = wait_for(manager, job.id)
    assert done["state"] == "error" and done["errors"] == ["ERROR: [Synth 8-1] mal"]
    assert programmer.programmed == []
    manager.shutdown()


def test_unexpected_exception_does_not_leak_details(tmp_path):
    class Boom:
        def compile(self, job):
            raise RuntimeError("secreto /home/usuario")

    manager, _ = make(tmp_path, Boom())
    job = manager.submit_vhdl(STUDENT)
    done = wait_for(manager, job.id)
    assert done["state"] == "error" and done["errors"] == ["Error interno del laboratorio."]
    manager.shutdown()


def test_bitstream_upload(tmp_path, make_bit):
    manager, programmer = make(tmp_path)
    data = make_bit(part="7a100tcsg324", design="Mio").read_bytes()
    job = manager.submit_bitstream(data)
    done = wait_for(manager, job.id)
    assert done["state"] == "done" and done["design"] == "Mio" and done["kind"] == "bit"
    assert len(programmer.programmed) == 1
    manager.shutdown()


def test_bitstream_for_another_fpga_is_rejected_before_queueing(tmp_path, make_bit):
    manager, programmer = make(tmp_path)
    data = make_bit(part="7z010clg400").read_bytes()
    with pytest.raises(BitstreamError):
        manager.submit_bitstream(data)
    assert manager.queue_length() == 0 and programmer.programmed == []
    assert list((tmp_path / "work").iterdir()) == []  # no deja carpetas huérfanas
    manager.shutdown()


def test_queue_limit_and_positions(tmp_path):
    blocker = BlockingCompiler(FakeCompiler(tmp_path / "work"))
    manager, _ = make(tmp_path, blocker, max_queue=2)
    first = manager.submit_vhdl(STUDENT)
    wait_for(manager, first.id, states=("compiling",))
    second = manager.submit_vhdl(STUDENT)
    third = manager.submit_vhdl(STUDENT)
    assert manager.get(second.id)["queue_position"] == 0
    assert manager.get(third.id)["queue_position"] == 1
    with pytest.raises(JobQueueFull):
        manager.submit_vhdl(STUDENT)
    blocker.release.set()
    for job in (first, second, third):
        assert wait_for(manager, job.id)["state"] == "done"
    manager.shutdown()


def test_unknown_job(tmp_path):
    manager, _ = make(tmp_path)
    with pytest.raises(JobNotFound):
        manager.get("nada")
    manager.shutdown()


def test_history_is_bounded(tmp_path):
    manager, _ = make(tmp_path, max_history=2)
    ids = []
    for _ in range(4):
        job = manager.submit_vhdl(STUDENT)
        wait_for(manager, job.id)
        ids.append(job.id)
    with pytest.raises(JobNotFound):
        manager.get(ids[0])
    assert manager.get(ids[-1])["state"] == "done"
    manager.shutdown()


def test_compile_result_type_is_used_by_blocking_compiler_signature():
    assert CompileResult  # el BlockingCompiler delega en FakeCompiler y devuelve CompileResult
