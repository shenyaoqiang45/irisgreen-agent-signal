# Examples

Each example runs without hardware using `--simulate` (a simulated projector), and against a real IrisGreen without it. Run them from anywhere in the repository; `_common.py` sets up the import paths.

| Example | Shows | Hardware needs |
|---|---|---|
| [basic-projection](basic-projection/main.py) | Connect, move a dot around the field, clear | IrisGreen |
| [image-projection](image-projection/main.py) | Project a picture full-field in two conversion modes | IrisGreen |

```text
python examples/basic-projection/main.py --simulate
python examples/image-projection/main.py --simulate

python examples/basic-projection/main.py --address F4:12:FA:B6:B7:CA
```

Every example turns the light off before exiting.
