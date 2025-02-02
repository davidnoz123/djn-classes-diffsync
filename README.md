# djn-classes-diffsync
A Python class to watch a local directory and efficiently synchronize text files to a remote Linux directory using compressed, unified diffing.
File change events are queued into a multiprocessing pool for faster processing time.

Not currently available in PyPI. Use locally installed git executable together with pip's version control system support (VCS) to install (or upgrade to) the latest code from the latest branch '0.1'.

```sh
pip install --upgrade git+https://github.com/davidnoz123/djn-classes-diffsync.git@0.1
```

Uninstall using:-

```sh
pip uninstall djn-classes-diffsync
```


```python
if __name__ == "__main__":        
    
    import os, tempfile, importlib, functools    
    import djn.classes.diffsync as diffsync
    
    remote_host, remote_user, password, key_filename, verbose = "<ip-address>", "<username>", "<key-file-password>", r"C:\key-file.pem", True

    get_ssh_client = functools.partial(diffsync.setup_ssh, remote_host, remote_user, password, key_filename=key_filename, verbose=verbose)   

    LOCAL_DIR, PATCH_DIR, REMOTE_DIR = os.getcwd(), os.path.join(tempfile.gettempdir(), "diff_sync_patches"), "./"

    diff_sync_handler = diffsync.DiffSyncHandler(get_ssh_client, LOCAL_DIR, REMOTE_DIR, PATCH_DIR, verbose=verbose)
    t, is_terminating = diffsync.DiffSyncHandler.start_monitoring(diff_sync_handler, patterns_files_accept=["*.py"])
    while t.is_alive():
        t.join(0.01) 
```
