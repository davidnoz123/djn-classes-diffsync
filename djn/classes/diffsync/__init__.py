

r"""

C:\analytics\projects\git\lexi\demos\venv\Scripts\python.exe

import runpy ; temp = runpy._run_module_as_main("__init__")

"""


def install_and_import(module_name, pip_name=None, user_install_otherwise_global=True, break_system_packages=False):
    """Attempts to import a module by string name and if it fails because there is no module by the name, then it attempts an install and another import."""
    import importlib, subprocess, sys, time
    mod = None
    try:
        mod = importlib.import_module(module_name)
    except ModuleNotFoundError:
        pass
    except ImportError as e:        
        raise Exception("install_and_import:Unexpected failure in importlib.import_module(package):%r:'%s'" % (package, str(e)))   
        
    if mod is None:
        
        # Run the pip install
        cmds = [sys.executable, "-m", "pip", "install"]
        if break_system_packages: 
            cmds.append("--break-system-packages") # error "externally-managed-environment" occurs when you try to install or modify Python packages using pip in a system-managed Python environment. This is common on Google Cloud virtual machines (VMs), especially those using Debian 12 (Bookworm) or Ubuntu 22.04+, where Python is managed by the system
        if user_install_otherwise_global:
            cmds.append("--user")                 
        subprocess.check_call(cmds + [pip_name or module_name])
        
        # It can happen that importlib.import_module does not work immediately .. handle this case
        sleep_secs = 0.02
        attempts = 0
        while sleep_secs < 5.12:
            try:
                mod = importlib.import_module(module_name)
                break
            except ImportError as e:
                # The package is not yet installed
                attempts += 1
                print(f"install_and_import:{e} import attempt:{attempts}:{e.__class__}:{e}")
                sleep_secs *= 2.0
            time.sleep(sleep_secs)
            
        if mod is None:
            raise Exception("ERROR:Failed to install package:'%s':pip_name=%r" % (module_name, pip_name))        
        
    return mod

class DiffSyncHandler:
    """Handles the creation, upload, and application of diff patches."""

    FMTX = "%-60s"

    def __init__(self, get_ssh_client, local_dir, remote_dir, patch_dir, cb_log_callback=None, verbose=False, mp_pool_size=8, max_file_locks=48):
        
        import os
        # Get arg refs
        self.get_ssh_client, self.local_dir, self.remote_dir, self.patch_dir, self.verbose, self.cb_log_callback = get_ssh_client, os.path.abspath(local_dir), remote_dir, os.path.abspath(patch_dir), verbose, cb_log_callback        
        
        # Assign locals
        self.ssh_client, self.sftp, self._file_path_2_status, self._remote_file_2_data, self._log_prefix_s, self.cb_log_callback_f = None, None, None, None, None, None
        
        self.use_gzip, self._log_calls = True, 0
        
        self.re_BEG_cksum, self.re_patch_not_found = None, None
            
        # Make sure we have our temp dir
        os.makedirs(self.patch_dir, exist_ok=True) 
        
        if isinstance(self.cb_log_callback, str):
            open(self.cb_log_callback, "w").close()
        
        import multiprocessing
        _mp_manager = multiprocessing.Manager()
        
        # Create a list of locks that we will use to protect one or more files from being processed at once.
        # Note that we must create these locks up front before we start running. They can't be created dynamically inside the subprocesses.
        # Note that in the case where large numbers of files being processed at once, the larger max_file_locks is, the less blocking there will be.
        file_path_2_lock_spare_locks_pos = _mp_manager.list() # Use a list to store the integer value
        file_path_2_lock_spare_locks_pos.append(-1) # Ready to increment for the first time
        
        file_path_2_lock_spare_locks = _mp_manager.list()        
        for k in range(max_file_locks):
            file_path_2_lock_spare_locks.append(_mp_manager.Lock())
        
        _mp_queue = multiprocessing.Queue()        
        _mp_pool = multiprocessing.Pool(mp_pool_size, self._run_mp_queue, (_mp_queue, _mp_manager.Lock(), _mp_manager.dict(), _mp_manager.dict(), file_path_2_lock_spare_locks, file_path_2_lock_spare_locks_pos))        
        
        self._mp_queue, self._mp_pool, self._mp_manager = _mp_queue, _mp_pool, _mp_manager
        
        self._file_path_2_status = dict() # The objects running self._run_mp_queue don't need this
         
    def _run_mp_queue(self, mp_queue, mp_lock, remote_file_2_data, file_path_2_lock, file_path_2_lock_spare_locks, file_path_2_lock_spare_locks_pos):
        self.mp_lock, self._remote_file_2_data = mp_lock, remote_file_2_data
        self.ssh_client = self.get_ssh_client()
        self.sftp = self.ssh_client.open_sftp()         
        try:
            # Continue running while the _mp_pool is not closed
            while True:
                file_path = mp_queue.get(True)   
                # Get the lock we'll use to protect this file from being processed simultaneously by two or more subprocesses.
                with self.mp_lock:
                    if file_path not in file_path_2_lock:
                        pos = file_path_2_lock_spare_locks_pos[0] = (file_path_2_lock_spare_locks_pos[0] + 1) % len(file_path_2_lock_spare_locks)
                        file_path_2_lock[file_path] = file_path_2_lock_spare_locks[pos]
                    file_lck = file_path_2_lock[file_path]
                with file_lck:
                    #print(file_lck, file_path)
                    tt = self.create_diff(file_path)
                    if tt:
                        rel_path, remote_file, patch_file, local_content = tt
                        self.upload_and_apply_patch(rel_path, remote_file, patch_file, local_content) 
        except KeyboardInterrupt:
            pass
            
            
    def log_prefix(self):
        if self._log_prefix_s is None:
            import os
            self._log_prefix_s = f"{self.__class__.__name__}:%09d:" % (os.getpid(),)
        import datetime
        self._log_calls += 1
        return f"{self._log_prefix_s}%06d:{datetime.datetime.utcnow().isoformat()}:" % (self._log_calls, )
        
    def cb_log_callback_default(self, s):
        self.cb_log_callback_f.write(f"{s}\n")        
        self.cb_log_callback_f.flush()
        
    def log_dump(self, s):
        try:
            if isinstance(self.cb_log_callback, str):
                self.cb_log_callback_f = open(self.cb_log_callback, "a")
                self.cb_log_callback = self.cb_log_callback_default        
                
            if self.cb_log_callback is not None:
                self.cb_log_callback(s)
                
        except BaseException as e:
            import io, traceback
            file = io.StringIO()
            traceback.print_tb(e.__traceback__, file=file)
            lf = "\n" 
            print(f"ERROR:Exception:log_dump:{e.__class__}:{e}{lf}{file.getvalue()}")            
        
    def log_log(self, s):
        s = f"{self.log_prefix()}{s}"
        if self.verbose: print(s)
        self.log_dump(s)

    def log_err(self, s):
        s = f"{self.log_prefix()}{s}"
        print(s)
        self.log_dump(s)            
                
    def close(self):
        p, f = self._mp_pool, self.cb_log_callback_f
        self._mp_pool, self.cb_log_callback_f = None, None
        if p is not None:
            p.close()
            #p.join()
        if f is not None:
            f.close()

    def __del__(self):
        try:
            self.close()
        except:
            pass
        
    def _cache_set(self, remote_file, cksum_and_len, content):
        #print(f"set {remote_file} {cksum_and_len}")
        with self.mp_lock:
            #print(f"{remote_file} {cksum_and_len} {len(content)}")
            self._remote_file_2_data[remote_file] = (cksum_and_len, content)    
        
    def _cache_get(self, remote_file, cksum_and_len):   
        #print(f"get {remote_file} {cksum_and_len}")
        # We have cached content for this file
        content = None
        with self.mp_lock:
            if remote_file not in self._remote_file_2_data:
                pass
                #print(f"{remote_file} {len(self._remote_file_2_data)}")
            else:
                tmp = self._remote_file_2_data[remote_file]
                cksum_and_len_cur = tmp[0]
                #print(f"{remote_file} {cksum_and_len_cur} {cksum_and_len}")
                if tmp[0] == cksum_and_len:
                    content = tmp[1]             
        if content is None:
            self.log_log(f"Downloading {self.FMTX} ..." % (remote_file,))
            import uuid, os
            temp_file = os.path.join(self.patch_dir, f"{uuid.uuid4().hex}.tmp")
            try:  
                self.sftp.get(remote_file, temp_file)
                content = open(temp_file, "r", encoding="utf-8").readlines()   
            except FileNotFoundError:
                content = []
            finally:
                if os.path.isfile(temp_file):
                    os.remove(temp_file)
            self.log_log(f"Downloading {self.FMTX} Complete" % (remote_file, ))   
        return content
        
    def create_diff(self, file_path):
        """Generates a unified diff file."""        
        try:
            import os  
            if self.ssh_client is None:
                self.ssh_client = self.get_ssh_client()
                self.sftp = self.ssh_client.open_sftp() 

            rel_path = os.path.relpath(file_path, self.local_dir)
            remote_file = os.path.join(self.remote_dir, rel_path).replace("\\", "/")
            patch_file = os.path.join(self.patch_dir, rel_path.replace('\\', '.').replace('/', '.') + f".patch{'.gz' if self.use_gzip else ''}")    
            
            # Fetch the remote file for comparison
            if self.verbose: self.log_log(f"Queryg file {self.FMTX} ..." % (remote_file, ))
            stdin, stdout, stderr = self.ssh_client.exec_command(f"cksum {remote_file}")  
            stdout_s, stderr_s = stdout.read().decode(), stderr.read().decode()
            if stderr_s.endswith("No such file or directory"):
                remote_content = []  # No remote file exists, treat as empty 
            else:
                cksum_and_len = tuple(stdout_s.split(" ")[:2])   
                remote_content = self._cache_get(remote_file, cksum_and_len)

            # Generate the diff  
            try:
                local_content = open(file_path, "r", encoding="utf-8").readlines()
            except BaseException as e:
                raise Exception(f"Failure read local file:{e.__class__}:{e}:'{file_path}'")
            import difflib
            diff = list(difflib.unified_diff(remote_content, local_content, fromfile=remote_file, tofile=remote_file)) 

            if diff is None:
                self.log_log(f"Queryg file {self.FMTX} Complete <NA>"  % (remote_file, ))    
                return None                
            else:
                self.log_log(f"Queryg file {self.FMTX} Complete {patch_file}" % (remote_file, ))   
                import gzip 
                if len(diff) > 0 and not diff[-1].endswith("\n"):
                    diff[-1] += "\n" # patch tool gives the error "**** malformed patch at line xyz" if the patch file doesn't end with a CR
                os.makedirs(os.path.dirname(patch_file), exist_ok=True)
                if self.use_gzip:
                    with gzip.open(patch_file, "w") as f: 
                        f.write(("".join(diff)).encode('utf-8'))                        
                else:
                    with open(patch_file, "w", encoding="utf-8") as f:
                        f.writelines(diff)                       
                return rel_path, remote_file, patch_file, local_content

        except Exception as e:
            import io, traceback
            file = io.StringIO()
            traceback.print_tb(e.__traceback__, file=file)
            lf = "\n" 
            self.log_err(f"Failed to create diff for {file_path}:{e.__class__}:{e}{lf}{file.getvalue()}")
            return None
            
    def handle_failure_uaap(self, command, stderr_s):
        if self.re_patch_not_found is None:
            import re
            self.re_patch_not_found = re.compile("patch: command not found")
        mm = self.re_patch_not_found.search(stderr_s)
        lf = '\n'
        if mm is not None:
            raise Exception(f"Missing 'patch' tool on remote server:'{';'.join(command)}':{stderr_s.split(lf)}")   
        else:
            raise Exception(f"Failure running command:'{';'.join(command)}':{stderr_s.split(lf)}")   

    def upload_and_apply_patch(self, rel_path, remote_file, patch_file, local_content):
        """Uploads the patch and applies it remotely."""
        try:
            import os            
            
            # Upload the patch file
            remote_patch = os.path.join(self.remote_dir, os.path.basename(patch_file))            
            self.log_log(f"Patchg file {self.FMTX} ..." % (remote_file,))                   
            self.sftp.put(patch_file, remote_patch)
            
            # Process the uploaded patch file
            command = []
            if self.use_gzip: command.append(f"gunzip -f {remote_patch}")
            command.append(f"patch --binary -p0 < {remote_patch[:-3] if self.use_gzip else remote_patch}"   )
            command.append(f" echo \"BEG_cksum\" ; echo `cksum {remote_file}`")
            while True:
                stdin, stdout, stderr = self.ssh_client.exec_command(';'.join(command))
                stdout_s, stderr_s = stdout.read().decode(), stderr.read().decode()
                if stderr_s == '':
                    break
                self.handle_failure_uaap(command, stderr_s)
            
            # Update the local cache
            if self.re_BEG_cksum is None:
                import re
                self.re_BEG_cksum = re.compile("BEG_cksum\n([0-9]+)\s+([0-9]+)\s", re.MULTILINE)            
            mm = self.re_BEG_cksum.search(stdout_s)
            if mm is None:
                #print(f"mm is None:{stdout_s.encode('utf-8')}")
                pass
            else:
                #print(f"mm is not None:{stdout_s.encode('utf-8')}")
                cksum_and_len = mm.groups()  
                self._cache_set(remote_file, cksum_and_len, local_content)
            
            self.log_log(f"Patchg file {self.FMTX} Complete" % (remote_file, ))   
        except Exception as e:
            import io, traceback
            file = io.StringIO()
            traceback.print_tb(e.__traceback__, file=file)
            lf = "\n"             
            self.log_err(f"Failed to apply patch {patch_file}:{e.__class__}:{e}{lf}{file.getvalue()}")

    def process_event(self, file_path):
        """Handles file change events."""
        import os
        mt = os.path.getmtime(file_path)
        if file_path in self._file_path_2_status and self._file_path_2_status[file_path] == mt:
            pass
        else:
            self._file_path_2_status[file_path] = mt
            self._mp_queue.put(file_path)
            
    @classmethod
    def start_monitoring(cls, diff_sync_handler, patterns_files_accept=None, patterns_files_ignore=None, is_pattern_glob_otherwise_regex=True):
        """Starts monitoring local files and syncing diffs to the remote machine."""
        
        install_and_import("watchdog")
        from watchdog.observers import Observer
        from watchdog.events import PatternMatchingEventHandler, RegexMatchingEventHandler # https://python-watchdog.readthedocs.io/en/stable/api.html#watchdog.events.PatternMatchingEventHandler
        
        x_MatchingEventHandler = PatternMatchingEventHandler if is_pattern_glob_otherwise_regex else RegexMatchingEventHandler
        
        import os  
        is_win = os.name == 'nt'
        
        if is_pattern_glob_otherwise_regex:
            kwargs = dict(case_sensitive=not is_win, patterns=patterns_files_accept, ignore_patterns=patterns_files_ignore)
        else:
            kwargs = dict(case_sensitive=not is_win, regexes=patterns_files_accept, ignore_regexes=patterns_files_ignore)        
        
        if True:
            # We want to find all the files that x_MatchingEventHandler will match 
            # and we want to trigger them all to be handled by diff_sync_handler
            # to upload the initial versions of the files to the remote server.
            
            # We're going to piggy-back on the logic in watchdog so we can avoid duplicating its file matching logic.
            # To do this we override the super().dispatch method of a single instance 
            # of x_MatchingEventHandler. Then, we pass all the files in diff_sync_handler.local_dir
            # to this instance and call diff_sync_handler._mp_queue.put for each file
            # matching the logic defined by patterns_files_accept, patterns_files_ignore and is_pattern_glob_otherwise_regex
            import watchdog
            if not x_MatchingEventHandler.__mro__[1] is watchdog.events.FileSystemEventHandler:
                raise Exception("not x_MatchingEventHandler.__mro__[1] is watchdog.events.FileSystemEventHandler")
            class _FileSystemEventHandlerWithOverriddenDispatchFunction(watchdog.events.FileSystemEventHandler):
                def dispatch(self, event):
                    diff_sync_handler._mp_queue.put(event.src_path)

            klass = type("x_MatchingEventHandlerWithOverriddenParent", (x_MatchingEventHandler, _FileSystemEventHandlerWithOverriddenDispatchFunction), {})
            meh = klass(**kwargs)
            
            for root, dirs, files in os.walk(diff_sync_handler.local_dir):
                for filename in files:
                    src_path = os.path.join(root, filename)
                    obj = watchdog.events.FileCreatedEvent(src_path)
                    meh.dispatch(obj)
        
        class MyEventHandler(x_MatchingEventHandler):
            """Forwards file events to DiffSyncHandler."""

            def __init__(self, _diff_sync_handler, **kwargs): # kwargs : patterns=None, ignore_patterns=None, ignore_directories=False, case_sensitive=False
                super().__init__(**kwargs)
                self._diff_sync_handler = _diff_sync_handler

            def on_modified(self, event):
                if not event.is_directory:
                    self._diff_sync_handler.process_event(event.src_path)

            def on_created(self, event):
                if not event.is_directory:
                    self._diff_sync_handler.process_event(event.src_path)
                    
        def _f(_diff_sync_handler, _is_terminating, **kwargs):
            observer = Observer()
            try:
                observer.schedule(MyEventHandler(_diff_sync_handler, **kwargs), _diff_sync_handler.local_dir, recursive=True)
                observer.start()
                import time
                while not _is_terminating.value:
                    time.sleep(1)
            except BaseException as e:
                _is_terminating.exception = e
                import io, traceback
                file = io.StringIO()
                traceback.print_tb(e.__traceback__, file=file)
                lf = "\n"             
                diff_sync_handler.log_err(f"start_monitoring:{e.__class__}:{e}{lf}{file.getvalue()}")                
            finally:
                observer.stop()
                #observer.join()
                
        class is_terminating_cls:
            def __init__(self):
                self.value, self.exception = False, None
                
        is_terminating = is_terminating_cls()

        import threading        
        t = threading.Thread(target=_f, args=(diff_sync_handler, is_terminating), kwargs=kwargs, daemon=True)
        t.start() 
        
        return t, is_terminating
        
    @classmethod    
    def start_debug_testing_modifys(cls, local_dir, _is_terminating, _lck):
        
        def _ff():
            import time, random
            rnd = random.Random(25)
            
            faker = install_and_import('faker')
            
            fake = faker.Faker()
            fake.seed_instance(42)
            
            # Generate a random paragraph
            def generate_paragraph(sentences=1):
                paragraph = []
                for _ in range(sentences):
                    sentence = f"{fake.name()} {rnd.choice(['lives in', 'works at', 'studies in'])} {fake.city()} and {rnd.choice(['loves', 'hates', 'enjoys'])} {fake.word()}."
                    paragraph.append(sentence)
                return " ".join(paragraph)

            # Create a realistic text file
            def create_text_file(filename, paragraphs=20):
                with open(filename, "w") as file:
                    for _ in range(paragraphs):
                        file.write(generate_paragraph() + "\n\n")
                        
            def modify_text_file(file_path, output_path, delete_prob=0.2, insert_prob=0.2, modify_prob=0.2):
                """
                Randomly modifies a text file by deleting lines, inserting new lines, and modifying words.
                
                Parameters:
                - file_path (str): Path to the input text file.
                - output_path (str): Path to save the modified text file.
                - delete_prob (float): Probability of deleting a line.
                - insert_prob (float): Probability of inserting a new line.
                - modify_prob (float): Probability of modifying a word in a line.
                """
                
                with open(file_path, "r", encoding="utf-8") as file:
                    lines = file.readlines()
                
                modified_lines = []
                
                for line in lines:
                    if random.random() < delete_prob:
                        continue  # Skip this line (deleting it)

                    # Optionally modify words in the line
                    words = line.split()
                    if words and random.random() < modify_prob:
                        idx = random.randint(0, len(words) - 1)
                        words[idx] = fake.word()  # Replace with a fake word
                        line = " ".join(words) + "\n"

                    modified_lines.append(line)

                    # Optionally insert a random new line after this line
                    if random.random() < insert_prob:
                        modified_lines.append(fake.sentence() + "\n")

                # Write the modified text to the output file
                with open(output_path, "w", encoding="utf-8") as file:
                    file.writelines(modified_lines)

                print(f"Modified file saved as: {output_path}")                        
            
            wd = os.path.join(local_dir, "start_debug_testing_modifys_tmp", *[fake.word() for i in range(rnd.randint(1, 5))])
            if os.path.isdir(wd):
                try:
                    import shutil
                    shutil.rmtree(wd)
                except:
                    pass                
            os.makedirs(wd, exist_ok=True)
            time.sleep(2.0)
            file_path = os.path.join(wd, "random_text.py")
            try:
                count = 0
                while not _is_terminating.value:
                    with _lck:
                        if count == 0:
                            print('Creating ...')
                            create_text_file(filename=file_path)
                            print('Creating Complete')
                        else:
                            print('Modifing ...')                            
                            modify_text_file(file_path, file_path, delete_prob=0.2, insert_prob=0.3, modify_prob=0.2)
                            print('Modifing Complete')                            
                        #break
                        count += 1
                    time.sleep(3.0)
            except BaseException as e:
                import io, traceback
                file = io.StringIO()
                traceback.print_tb(e.__traceback__, file=file)
                lf = "\n"             
                print(f"ERROR:Exception:start_debug_testing__monitor:{e.__class__}:{e}{lf}{file.getvalue()}")                     
            finally:
                pass
                
        import threading                
        t = threading.Thread(target=_ff, daemon=True)
        t.start()        
        
    @classmethod    
    def start_debug_testing_monitor(cls, local_dir, _is_terminating, _lck, remote_dir, work_dir, get_ssh_client, log_file_name):
        
        def _ff():
            import time, re, uuid, difflib
            
            re_match_patch_complete = re.compile("Patchg file\s+(.*)\s+Complete")
            ssh_client, fd = None, None
            skip_delete = False
            try:
                ssh_client = get_ssh_client()
                sftp = ssh_client.open_sftp() 
                fd = open(log_file_name, "r")
                curr_len = 0
                while not _is_terminating.value:
                    time.sleep(1.0)
                    bb = os.path.getsize(log_file_name)
                    if curr_len != bb:
                        ss = fd.read(bb - curr_len + 1)
                        curr_len = bb
                        with _lck:
                            print('Checking ...')
                            for m in re_match_patch_complete.finditer(ss):
                                if _is_terminating.value: break
                                remote_file = os.path.join(remote_dir, m.groups()[0].strip())
                                temp_file = os.path.join(work_dir, f"{uuid.uuid4().hex}.dbg")
                                try:
                                    try:
                                        sftp.get(remote_file, temp_file)
                                    except BaseException as e:
                                        print(f"Faliure running sftp.get(remote_file, temp_file):{e.__class__}:{e}:'{remote_file}':'{temp_file}'")
                                        raise
                                    locl_file = os.path.abspath(os.path.join(local_dir, remote_file))
                                    with open(temp_file, "r") as ff:
                                        temp_line = ff.readlines()
                                    with open(locl_file, "r") as ff:
                                        locl_line= ff.readlines()                                    
                                    diff = list(difflib.ndiff(temp_line, locl_line))
                                    
                                    recs_pl = [x[2:] for x in diff if x.startswith('+ ')]
                                    recs_mn = [x[2:] for x in diff if x.startswith('- ')]
                                    print(recs_pl)
                                    print(recs_mn)
                                    if False:
                                        print(f"fcompare {temp_file} {locl_file}")
                                        _is_terminating.value = True
                                        skip_delete = True
                                finally:
                                    if not skip_delete and os.path.exists(temp_file):
                                        os.remove(temp_file)
                            print('Checking Complete')
            except BaseException as e:
                import io, traceback
                file = io.StringIO()
                traceback.print_tb(e.__traceback__, file=file)
                lf = "\n"             
                print(f"ERROR:Exception:start_debug_testing__monitor:{e.__class__}:{e}{lf}{file.getvalue()}")                     
            finally:
                if fd: fd.close()
                if ssh_client: ssh_client.close()
                
                
        import threading                
        t = threading.Thread(target=_ff, daemon=True)
        t.start()
            
        
def setup_ssh(remote_host, remote_user, password, key_filename=None, verbose=False):
    if verbose: print(f"Connecting {remote_user}@{remote_host} ...")
    paramiko = install_and_import("paramiko")
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(remote_host, username=remote_user, password=password, key_filename=key_filename) 
    if verbose: print(f"Connecting {remote_user}@{remote_host} Complete")
    return ssh   

def main():    
    
    
    import os, tempfile, re, functools, argparse

    parser = argparse.ArgumentParser(description="Watch a local directory and efficiently and recursively synchronize text files to a remote Linux directory using compressed, unified diffing.")

    # Add arguments with default values
    parser.add_argument("-r", "--host", type=str, help="remote host IP address")
    parser.add_argument("-u", "--user", type=str, help="username")
    parser.add_argument("-d", "--remote_dir", type=str, default="./" , help="remote directory (default: ./)")
    parser.add_argument("-i", "--ssh_key_filename", type=str, default=None, help="SSH key file name (default: <none>)")
    parser.add_argument("-l", "--log_file_name", type=str, default=None, help="log file name (default: <none>)")
    parser.add_argument("-p", "--password_env_var_name", type=str, default='REMOTE_PASSWORD', help="environment variable containing the password (default: REMOTE_PASSWORD)")
    parser.add_argument('-v', '--verbose', action='store_true', help="echo log messages to the console")
    
    args = parser.parse_args()

    # Configuration for remote        
    REMOTE_HOST = args.host
    REMOTE_USER = args.user
    REMOTE_PASSWORD = os.environ[args.password_env_var_name] # Get the password from an environment variable
    REMOTE_DIR = args.remote_dir

    # Configuration for local
    verbose = args.verbose    
    LOCAL_DIR = os.getcwd() # Use the working directory
    PATCH_DIR = os.path.join(tempfile.gettempdir(), "diff_sync_patches")  # To store patch files before upload
    patterns_files_ignore = None     
    patterns_files_accept = ["*.py"]
    #patterns_files_accept = [".*\.py"]    
    is_pattern_glob_otherwise_regex = True    
    key_filename = args.ssh_key_filename 
    cb_log_callback = args.log_file_name    
        
    if False:
        REMOTE_HOST = '34.59.56.98'
        REMOTE_USER = 'g1davidnoz'
        LOCAL_DIR = r"C:\analytics\projects\fl\git"
        key_filename = r"C:\analytics\projects\git\lunk\g1davidnoz-01.pem"
        cb_log_callback = "xxlog.txt"    
        # ssh g1davidnoz@34.59.56.98  -i C:\analytics\projects\git\lunk\g1davidnoz-01.pem     


    kwargs = dict(verbose=verbose, mp_pool_size=8, max_file_locks=48) # Todo : Hook these to the argparse    
    
    global install_and_import
    install_and_import = functools.partial(install_and_import)         
    
    # Make sure paramiko is installed
    install_and_import("paramiko")    
    
    # Create a function we can pass around to create the ssh_client
    get_ssh_client = functools.partial(setup_ssh, REMOTE_HOST, REMOTE_USER, REMOTE_PASSWORD, key_filename=key_filename, verbose=verbose)      
         
    if True:    
        # Code to setup software required on remote computer 
        if verbose: print("Running Remote Installations ...") 
        command = []
        command.append("sudo apt install -y patch")         # REQUIRED Linux VMs probably don't come with the 'patch' tool
        #command.append("sudo apt install -y python3-pip")   # OPTIONAL Linux VMs probably don't come with pip 
        stderr_s, ssh_client = "", get_ssh_client()
        try:
            stdin, stdout, stderr = ssh_client.exec_command(";".join(command))
            for s in stdout:
                if verbose: print(s, end="")
            stderr_s = stderr.read().decode()
        finally:
            ssh_client.close()             
        if stderr_s.find("E: ") > 0:
            raise Exception(f"Failure running commands on remote server:{stderr_s.encode()}:{command}")            
        if verbose: print("Running Remote Installations Complete") 
        
    # Start the watch
    import threading
    _lck = threading.Lock()
    diff_sync_handler, is_terminating = None, None          
    try:
        diff_sync_handler = DiffSyncHandler(get_ssh_client, LOCAL_DIR, REMOTE_DIR, PATCH_DIR, cb_log_callback=cb_log_callback, **kwargs)
        t, is_terminating = DiffSyncHandler.start_monitoring(diff_sync_handler, patterns_files_accept=patterns_files_accept, patterns_files_ignore=patterns_files_ignore, is_pattern_glob_otherwise_regex=is_pattern_glob_otherwise_regex)
        if False and isinstance(cb_log_callback, str):
            # This code runs the randomised testing
            DiffSyncHandler.start_debug_testing_monitor(LOCAL_DIR, is_terminating, _lck, REMOTE_DIR, PATCH_DIR, get_ssh_client, cb_log_callback)        
            DiffSyncHandler.start_debug_testing_modifys(LOCAL_DIR, is_terminating, _lck)        
        while t.is_alive():
            t.join(0.01)         
    finally:
        if is_terminating is not None:
            is_terminating.value = True
            while t.is_alive(): 
                t.join(0.01)
            if diff_sync_handler is not None:
                diff_sync_handler.close()
                
if __name__ == "__main__":
    
    main()
    
