# djn-classes-diffsync
A Python class to watch a local directory and efficiently synchronize text files to a remote Linux directory using compressed, unified diffing.
File change events are queued into a multiprocessing pool for faster processing time.

Not currently available in PyPI. Use locally installed git executable together with pip's version control system support (VCS) to install (or upgrade to) the latest code from this branch.

```sh
pip install --upgrade git+https://github.com/davidnoz123/djn-classes-diffsync.git@0.1
```

Uninstall using:-

```sh
pip uninstall djn-classes-diffsync
```

Command line interface on Windows:-

```sh
python.exe <python-installation-root>\Lib\site-packages\djn\classes\diffsync\__init__.py -h

usage: __init__.py [-h] [-r HOST] [-u USER] [-d REMOTE_DIR] [-i SSH_KEY_FILENAME] [-l LOG_FILE_NAME] [-P PASSWORD] [-p PASSWORD_ENV_VAR_NAME] [-v]

Watch a local directory and efficiently and recursively synchronize text files to a remote Linux directory using compressed, unified diffing.

options:
  -h, --help            show this help message and exit
  -r HOST, --host HOST  remote host IP address
  -u USER, --user USER  username
  -d REMOTE_DIR, --remote_dir REMOTE_DIR
                        remote directory (default: ./)
  -i SSH_KEY_FILENAME, --ssh_key_filename SSH_KEY_FILENAME
                        SSH key file name (default: <none>)
  -l LOG_FILE_NAME, --log_file_name LOG_FILE_NAME
                        log file name (default: <none>)
  -P PASSWORD, --password PASSWORD
                        password
  -p PASSWORD_ENV_VAR_NAME, --password_env_var_name PASSWORD_ENV_VAR_NAME
                        environment variable containing the password (default: REMOTE_PASSWORD)
  -v, --verbose         echo log messages to the console

```

Command line example on Windows:-
```sh
python.exe <python-installation-root>\Lib\site-packages\djn\classes\diffsync\__init__.py -r <ip-address> -u <username> -P <password> -i C:\key_file.pem -v
```

Library example:-

```python
if __name__ == "__main__":        
    
    import os, tempfile, functools    
    import djn.classes.diffsync as diffsync

    # Configure the connection
    remote_host, remote_user, password, key_filename, verbose = "<ip-address>", "<username>", "<key-file-password>", r"C:\key-file.pem", True

    # Create a parameterless function we can pass to the multiprocessing pool functions to create the SSH clients
    get_ssh_client = functools.partial(diffsync.setup_ssh, remote_host, remote_user, password, key_filename=key_filename, verbose=verbose)   

    # Point to the target directories
    LOCAL_DIR, PATCH_DIR, REMOTE_DIR = os.getcwd(), os.path.join(tempfile.gettempdir(), "diff_sync_patches"), "./"

    print("Ctrl-C to terminate")
    
    diff_sync_handler, is_terminating = None, None       
    try:
        diff_sync_handler = diffsync.DiffSyncHandler(get_ssh_client, LOCAL_DIR, REMOTE_DIR, PATCH_DIR, verbose=verbose)
        t, is_terminating = diffsync.DiffSyncHandler.start_monitoring(diff_sync_handler, patterns_files_accept=["*.py"])
        while t.is_alive():
            t.join(0.01) 
    finally:
        # Clean up to avoid screeds of messages from multiprocessing etc.
        if is_terminating is not None:
            is_terminating.value = True
            while t.is_alive(): 
                t.join(0.01)
        if diff_sync_handler is not None:
            diff_sync_handler.close()
```
**NOTE**: The tool requires the Unix utility 'patch' to be installed on the server. This is installed automatically in the command line version of the code. See `def install_dependencies_on_server(get_ssh_client, verbose=False)` in `__init__.py` for details.

## Motivation
Developing Python code on remote machines can be cumbersome due the lag as the local source changes are uploaded to the server and the interpreter starts up and runs your code.
Of course, this can be an issue for remote development in any language.
This tool provides an alternative to using, say, VSCode, PyCharm or MobaXterm for remote development.


The idea is to set the tool running and edit your local files as usual.
Then in an SSH window with a Python interpreter running, you run the following command for Python to load and run your latest code.
```sh
>>> import runpy ; temp = runpy._run_module_as_main("your_module")
```

When you have run the command once, then it is just a matter of typing Up Arrow and Enter.


This approach can be easily extended to load changes to mulitple Python files at once before re-running your program (using `importlib.reload(your_other_module)`).


A word of caution about this approach is that the interpreter is not restarted between runs and care is sometimes needed to avoid confusing results when running complex code configurations.


## ToDo

Soon to add a function that can be called from the remote interpreter before your call to `temp = runpy._run_module_as_main("your_module")` to wait until all code changes have finished uploading.


## Feedback
Have questions or suggestions? [Open an issue](https://github.com/davidnoz123/djn-classes-diffsync/issues).


