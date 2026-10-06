"""Opt-in drop regression using generated files; never performs a transfer.

PostMessage is essential: Tk's mainloop must dispatch the native callback.
Synchronous SendMessage from Python did not reproduce the original abort.
"""
import ctypes
from ctypes import wintypes as w
import json
from pathlib import Path
import struct
import tempfile
import time


def run(root, app, output):
    k = ctypes.WinDLL('kernel32', use_last_error=True)
    u = ctypes.WinDLL('user32', use_last_error=True)
    k.GlobalAlloc.argtypes = [w.UINT, ctypes.c_size_t]
    k.GlobalAlloc.restype = w.HGLOBAL
    k.GlobalLock.argtypes = [w.HGLOBAL]
    k.GlobalLock.restype = ctypes.c_void_p
    k.GlobalUnlock.argtypes = [w.HGLOBAL]
    k.GlobalFree.argtypes = [w.HGLOBAL]
    u.PostMessageW.argtypes = [w.HWND, w.UINT, w.WPARAM, w.LPARAM]
    u.PostMessageW.restype = w.BOOL

    def post(paths):
        payload = struct.pack('<IiiII', 20, 0, 0, 0, 1)
        payload += ('\0'.join(map(str, paths)) + '\0\0').encode('utf-16-le')
        handle = k.GlobalAlloc(0x42, len(payload))
        if not handle:raise ctypes.WinError(ctypes.get_last_error())
        pointer = k.GlobalLock(handle)
        if not pointer:
            k.GlobalFree(handle)
            raise ctypes.WinError(ctypes.get_last_error())
        ctypes.memmove(pointer, payload, len(payload))
        k.GlobalUnlock(handle)
        if not u.PostMessageW(app.drop.hwnd, 0x233, handle, 0):
            k.GlobalFree(handle)
            raise ctypes.WinError(ctypes.get_last_error())
        # Ownership passes to DragFinish in FileDrop's native callback.

    errors = []
    received = []
    results = {}
    finished = False

    def capture_error(kind, value, traceback):
        errors.append(str(value))
        root.quit()

    def accept(paths):
        received.append(paths)
        app.add_sources(paths)

    root.report_callback_exception = capture_error
    app.drop.callback = accept

    with tempfile.TemporaryDirectory(prefix='c71-ui-drop-test-') as folder:
        folder = Path(folder)
        files = [folder / '文書 test.docx', folder / '画像 test.png']
        for f in files:f.write_bytes(b'generated fixture, selection only')
        directory = folder / '資料 folder'
        directory.mkdir()
        files.append(directory)

        def steps():
            post(files)
            yield lambda: len(received) == 1
            assert app.sources == list(map(str, files))
            results['asynchronous_mainloop_unicode_files_and_folder'] = True

            for _ in range(50):post(files)
            yield lambda: len(received) == 51
            assert app.sources == list(map(str, files))
            results['repeated_native_drops_without_duplicates'] = 50

            app.busy = True
            post([folder / 'busy drop.txt'])
            yield lambda: len(received) == 52
            assert app.sources == list(map(str, files))
            app.busy = False
            results['busy_drop_ignored'] = True

            for mode in ['USB', '2次元コード', 'MIDI']:
                app.transport.set(mode)
                app.transport_changed()
                yield lambda: True
                if mode == 'MIDI':assert app.midi_options.winfo_ismapped()
                elif mode == '2次元コード':assert app.optical_options.winfo_ismapped()
                else:assert not app.midi_options.winfo_ismapped()
            results['three_transport_controls'] = True

            app.files.selection_set(0)
            app.remove_sources()
            assert app.sources == list(map(str, files[1:]))
            app.clear_sources()
            assert not app.sources
            post([files[0]])
            yield lambda: len(received) == 53
            assert app.sources == [str(files[0])]
            results['clear_then_drop_again'] = True

            poll_id = app.drop.poll_id
            app.drop.close()
            app.drop.close()
            assert poll_id not in root.tk.call('after', 'info')
            assert app.drop.closed
            results['idempotent_close_cancels_drop_timer'] = True
            results['native_drop_messages'] = len(received)
            results['no_transfer_performed'] = True

        sequence = steps()
        condition = None
        deadline = 0

        def tick():
            nonlocal condition, deadline, finished
            try:
                if condition is not None and not condition():
                    if time.monotonic() > deadline:
                        raise AssertionError('Timed out waiting for asynchronous drop')
                    root.after(20, tick)
                    return
                condition = next(sequence)
                deadline = time.monotonic() + 5
                root.after(20, tick)
            except StopIteration:
                finished = True
                root.quit()
            except Exception as error:
                capture_error(type(error), error, error.__traceback__)

        root.after(100, tick)
        root.mainloop()
        app.busy = False
        app.close()
        assert not errors, errors
        assert finished, 'Mainloop ended before diagnostics completed'
        Path(output).write_text(json.dumps(results, indent=2), encoding='utf-8')
