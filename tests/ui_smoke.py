"""Run the asynchronous drop regression in the source build."""
import faulthandler
from pathlib import Path
import sys
import tkinter as tk

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'desktop'))
from transfer_ui import TransferApp
from drop_diagnostics import run

if __name__ == '__main__':
    faulthandler.enable()
    root = tk.Tk()
    run(root, TransferApp(root), sys.argv[1])
