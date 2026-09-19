# Custom Recursive fonts

Install the fonts in [`ttf/`](ttf). This directory contains the custom builds:

- **Recursive Duo Sans**: Linear roman, Casual italic.
- **Recursive Linear Sans**: Linear roman and italic.
- **Recursive Casual Sans**: Casual roman and italic.

Each family has eight weights, each with roman and italic faces: 48 TTFs total.
All include the custom time-colon behavior and italic feature settings described
in the [build notes](../custom-duo-sans/README.md).

Rebuild from the repository root:

```sh
python3 custom-duo-sans/build.py
```

The upstream font inputs are tracked separately under
[`custom-duo-sans/sources`](../custom-duo-sans/sources). This folder contains only
custom output fonts, their [license](OFL.txt), and this README.
