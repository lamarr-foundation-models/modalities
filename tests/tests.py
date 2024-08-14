import argparse
import os
import subprocess
from os.path import isdir, isfile, join
from pathlib import Path

_ROOT_DIR = Path(__file__).parents[1]


def clear_getting_started_example_output_directory(output_directory):
    assert isdir(output_directory), f"ERROR! {output_directory} does not exist."
    output_files = [
        "redpajama_v2_samples_512_train.idx",
        "redpajama_v2_samples_512_test.idx",
        "redpajama_v2_samples_512_train.pbin",
        "redpajama_v2_samples_512_test.pbin",
    ]
    print()
    for output_file in output_files:
        output_file_path = join(output_directory, output_file)
        assert isfile(output_file_path), f"ERROR! {output_file_path} does not exist."
        os.remove(output_file_path)
        print(f"> removed {output_file_path}")


def main(cpu: bool = False, single_gpu: bool = False, multi_gpu: bool = False, devices: str = "0,1"):
    """
    Run tests on cpu, single gpu and multiple gpus

    Examples:
    python tests/tests.py: run CPU tests + single-GPU tests on GPU 0 + multi-GPU tests on GPUs 0/1
    python tests/tests.py --devices 4,5: same as above but using devices 4/5
    python tests/tests.py --cpu: run CPU tests
    python tests/tests.py --single-gpu --devices 3: run CPU tests + single-GPU tests on GPU 3
    python tests/tests.py --multi-gpu --devices 3,4: run multi-GPU tests on GPUs 3/4
    """
    # parse input
    if not cpu and not single_gpu and not multi_gpu:  # run all tests
        cpu, single_gpu, multi_gpu = True, True, True
    if single_gpu:  # cpu & single_gpu are both executed together via pytest
        cpu = True
    try:
        devices = [int(device) for device in devices.split(",")]  # e.g. '0,1' -> [0, 1]
    except ValueError:
        exit(f"ERROR! devices needs to be a string of comma-separated ints, e.g. '0,1'. Specified devices = {devices}")
    devices = devices if len(devices) <= 2 else devices[:2]  # use max 2 devices

    # check input
    if single_gpu and len(devices) < 1:
        exit(f"ERROR! Need at least 1 device to run single_gpu tests. Specified devices = {devices}")
    if multi_gpu and len(devices) < 2:
        exit(f"ERROR! Need 2 devices to run multi_gpu tests. Specified devices = {devices}")

    # start
    print(f"> TESTS ON          CPU: {cpu}")
    print(f"> TESTS ON   SINGLE GPU: {single_gpu} " + f"(device={devices[0] if single_gpu else None})")
    print(f"> TESTS ON MULTIPLE GPU: {multi_gpu} " + f"(devices={devices if multi_gpu else None})")

    # run cpu / single-gpu tests
    if cpu or single_gpu:
        print("\n=== RUN CPU & SINGLE-GPU TESTS ===" if single_gpu else "\n=== RUN CPU TESTS ===")
        command_unit_tests = (
            f"cd {_ROOT_DIR} && CUDA_VISIBLE_DEVICES={devices[0] if single_gpu else None} python -m pytest"
        )
        print(command_unit_tests)
        subprocess.run(command_unit_tests, shell=True, capture_output=False, text=True)

    # run multi-gpu tests
    if multi_gpu:
        # distributed tests
        print("\n=== RUN MULTI-GPU TESTS ===")
        run_distributed_tests_directory = _ROOT_DIR / "tests"
        run_distributed_tests_script = _ROOT_DIR / "tests" / "run_distributed_tests.sh"
        assert isfile(run_distributed_tests_script), f"ERROR! {run_distributed_tests_script} does not exist."
        command_end_to_end_tests = (
            f"cd {run_distributed_tests_directory}; bash run_distributed_tests.sh {devices[0]} {devices[1]}"
        )
        print(command_end_to_end_tests)
        subprocess.run(command_end_to_end_tests, shell=True, capture_output=False, text=True)

        # getting started example
        print("\n=== RUN GETTING STARTED EXAMPLE ===")
        run_getting_started_example_directory = _ROOT_DIR / "examples" / "getting_started"
        run_getting_started_example_script = (
            _ROOT_DIR / "examples" / "getting_started" / "run_getting_started_example.sh"
        )
        assert isfile(
            run_getting_started_example_script
        ), f"ERROR! {run_getting_started_example_script} does not exist."
        command_getting_started_example = (
            f"cd {run_getting_started_example_directory}; bash run_getting_started_example.sh {devices[0]} {devices[1]}"
        )
        print(command_getting_started_example)
        subprocess.run(command_getting_started_example, shell=True, capture_output=False, text=True)

        output_directory = join(run_getting_started_example_directory, "data", "mem_map")
        clear_getting_started_example_output_directory(output_directory)

    print("\n=== DONE ===")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Description of your program")
    parser.add_argument("--cpu", action=argparse.BooleanOptionalAction, help="Do cpu testing.")
    parser.add_argument("--single-gpu", action=argparse.BooleanOptionalAction, help="Do single GPU testing.")
    parser.add_argument("--multi-gpu", action=argparse.BooleanOptionalAction, help="Do multi GPU testing.")
    parser.add_argument("--devices", type=str, default="0,1")
    args = vars(parser.parse_args())
    args = {k: v if v is not None else False for k, v in args.items()}  # None -> False
    main(**args)
