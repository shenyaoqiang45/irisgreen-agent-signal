# Examples

Each example runs without hardware using `--simulate` (a simulated projector, camera and wall), and against a real IrisGreen without it. Run them from anywhere in the repository; `_common.py` sets up the import paths.

| Example | Shows | Hardware needs |
|---|---|---|
| [basic-projection](basic-projection/main.py) | Connect, move a dot around the field, clear | IrisGreen |
| [image-projection](image-projection/main.py) | Project a picture full-field, then fit it onto a wall region found through calibration | IrisGreen + camera |
| [object-tracking](object-tracking/main.py) | Vision to physical: a VLM finds the object, the laser dot follows it | IrisGreen + camera (+ VLM, or pass `--bbox`) |

```text
python examples/basic-projection/main.py --simulate
python examples/image-projection/main.py --simulate
python examples/object-tracking/main.py --simulate

python examples/basic-projection/main.py --address F4:12:FA:B6:B7:CA
python examples/object-tracking/main.py --camera 0 --intent "the red-bordered patch"
```

The real VLM is configured by environment variables (`IRISGREEN_VLM_URL`, `IRISGREEN_VLM_KEY`, `IRISGREEN_VLM_MODEL`) and may be any OpenAI-compatible endpoint. Without a VLM, pass `--bbox X Y W H` in camera pixels.

Every example turns the light off before exiting. They are exercised by [tests/integration](../tests/integration) in simulation.
