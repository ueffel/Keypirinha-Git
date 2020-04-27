import keypirinha as kp
import keypirinha_util as kpu
import globex
import filefilter
import subprocess
import os
import json
import time

class Git(kp.Plugin):
    CONFIG_PREFIX_SCAN_PATH="scan_path/"
    CONFIG_PREFIX_CMD="cmd/"
    CONFIG_PREFIX_CMD_ALL="cmd_all/"
    COMMAND_RESCAN="rescan"
    COMMAND_REMOVE_OLD="remove_old"
    COMMAND_GARBAGE_COLLECTION="gc"
    COMMAND_GARBAGE_COLLECTION_ALL="gc_all"
    COMMAND_OPEN_GIT_BASH="open_git_bash"
    COMMAND_CMD_ALL="cmd_all"
    COMMAND_RENAME="rename"
    ARGS_TOP_LEVEL="rev-parse --show-toplevel"
    ARGS_COUNT_OBJECT="count-objects"
    ARGS_GC="gc"

    def __init__(self):
        super().__init__()
        self._debug = True
        self._git_path = "git"
        self._git_bash_path = None
        self._scan_paths = []
        self._cmds = []
        self._cmds_all = []
        self._git_repos = []

    def on_start(self):
        self._read_config()
        self.on_catalog()

    def on_events(self, flags):
        if flags & kp.Events.PACKCONFIG:
            self._read_config()
            self.on_catalog()

    def _check_git_path(self):
        self.dbg("_check_git_path")
        if os.path.isabs(self._git_path) and os.path.isfile(self._git_path):
            self._try_set_default_icon(self._git_path)
            return True
        else:
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            proc = subprocess.run("where " + self._git_path, stdout=subprocess.PIPE, startupinfo=startupinfo)
            if proc.returncode != 0:
                return False
            lines = proc.stdout.decode().splitlines()
            if len(lines) == 0:
                return False
            self._try_set_default_icon(lines[0])
            return True
        return False

    def _try_set_default_icon(self, abs_git_path):
        check_path = os.path.join(os.path.dirname(os.path.dirname(abs_git_path)), "git-bash.exe")
        self.dbg(check_path)
        if os.path.exists(check_path):
            self._git_bash_path = check_path
            self.set_default_icon(self.load_icon("@{},0".format(self._git_bash_path)))
        check_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(abs_git_path))), "git-bash.exe")
        self.dbg(check_path)
        if os.path.exists(check_path):
            self._git_bash_path = check_path
            self.set_default_icon(self.load_icon("@{},0".format(self._git_bash_path)))
        check_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(abs_git_path)))), "git-bash.exe")
        self.dbg(check_path)
        if os.path.exists(check_path):
            self._git_bash_path = check_path
            self.set_default_icon(self.load_icon("@{},0".format(self._git_bash_path)))

    def _read_config(self):
        self.dbg("Reading config")
        settings: kp.Settings = self.load_settings()

        self._debug = settings.get_bool("debug", "main", False)

        self._git_path = settings.get("git_exe", "main", "git")
        if not self._check_git_path():
            self.err("no git executable found!")

        self._scan_paths = []
        self._cmds = []
        self._cmds_all = []
        for section in settings.sections():
            if section.startswith(self.CONFIG_PREFIX_SCAN_PATH):
                keys = settings.keys(section)
                scan_path = {}
                if "paths" not in keys:
                    continue
                scan_path["name"] = section.lstrip(self.CONFIG_PREFIX_SCAN_PATH)
                scan_path["paths"] = settings.get_multiline("paths", section)
                depth = settings.get_int("depth", section, -1)
                scan_path["depth"] = depth
                excludes = settings.get_multiline("excludes", section)
                scan_path["excludes"] = excludes
                self._scan_paths.append(scan_path)
            elif section.startswith(self.CONFIG_PREFIX_CMD):
                cmd = settings.get_stripped("cmd", section)
                if not cmd:
                    self.err(section, "has no 'cmd'")
                    continue
                if os.path.isabs(cmd) and not os.path.exists(cmd):
                    self.dbg(section, "cmd is absolute path and does not exist", cmd)
                    continue
                command = GitCommand(section.lstrip(self.CONFIG_PREFIX_CMD),
                                     cmd.format(git_exe=self._git_path),
                                     settings.get("label", section, section.lstrip(self.CONFIG_PREFIX_CMD)),
                                     settings.get("args", section, '"{repo_path}"'),
                                     settings.get("cwd", section, None))
                self._cmds.append(command)
            elif section.startswith(self.CONFIG_PREFIX_CMD_ALL):
                cmd = settings.get_stripped("cmd", section)
                if not cmd:
                    self.err(section, "has no 'cmd'")
                    continue
                if os.path.isabs(cmd) and not os.path.exists(cmd):
                    self.dbg(section, "cmd is absolute path and does not exist", cmd)
                    continue
                command = GitCommand(section.lstrip(self.CONFIG_PREFIX_CMD_ALL),
                                     cmd.format(git_exe=self._git_path),
                                     settings.get("label", section, section.lstrip(self.CONFIG_PREFIX_CMD_ALL)),
                                     settings.get("args", section, ""))
                self._cmds_all.append(command)

        self.dbg("scan_paths", self._scan_paths)
        self.dbg("cmds", self._cmds)
        self.dbg("cmds_all", self._cmds_all)

    def _rescan(self):
        self.dbg("rescan")
        start_time = time.time()
        git_repos = []
        remove_repos = []
        for scan_path in self._scan_paths:
            start_time_scan_path = time.time()
            scan_path_repos = []
            for path in scan_path["paths"]:
                for entry in globex.iglobex(path+"/**/.git/", recursivity=scan_path["depth"], include_hidden=True):
                    filtered = False
                    for exclude in scan_path["excludes"]:
                        filter = filefilter.create_filter(exclude)
                        if filter.match(entry):
                            filtered = True
                    if filtered:
                        continue

                    git_repo = self._get_top_level(os.path.dirname(entry))
                    if git_repo:
                        scan_path_repos.append(GitRepo(os.path.basename(git_repo), git_repo))
            git_repos.extend(scan_path_repos)
            elapsed = time.time() - start_time_scan_path
            self.info('Found {} git repositories in "{}" in {:0.1f} seconds'.format(len(scan_path_repos), scan_path["name"], elapsed))

        self.dbg(git_repos)
        for repo in self._git_repos:
            if repo not in git_repos:
                remove_repos.append(repo)
        self.dbg(remove_repos)
        for repo in remove_repos:
            self._git_repos.remove(repo)
        for repo in git_repos:
            if repo not in self._git_repos:
                self._git_repos.append(repo)

        self.dbg(self._git_repos)
        self._save_repos()

        elapsed = time.time() - start_time
        self.info("Found {} git repositories in {:0.1f} seconds".format(len(self._git_repos), elapsed))

    def _save_repos(self):
        cache_path = self.get_package_cache_path(True)
        with open(os.path.join(cache_path, "repos.json"), "w") as repos:
            json.dump(self._git_repos, repos, indent=4, sort_keys=True, cls=GitRepoEncoder)

    def _get_top_level(self, dir):
        self.dbg("get_top_level", dir)
        if not os.path.exists(dir):
            return ""
        if not os.path.isdir(dir):
            cwd = os.path.dirname(dir)
        else:
            cwd = dir

        command = '"{}" {}'.format(self._git_path, self.ARGS_TOP_LEVEL)
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        proc = subprocess.run(command, cwd=cwd, stdout=subprocess.PIPE, startupinfo=startupinfo)
        if proc.returncode == 0:
            return os.path.normpath(proc.stdout.decode().rstrip("\r\n"))
        else:
            self.dbg("command returned", proc.returncode, "for", cwd)

        return None

    def on_catalog(self):
        cache_path = self.get_package_cache_path(False)
        repos_path = os.path.join(cache_path, "repos.json")
        if os.path.exists(repos_path):
            with open(repos_path, "r") as repos:
                self._git_repos = json.load(repos, cls=GitRepoDecoder)
        else:
            self._rescan()

        catalog = []
        catalog.append(self.create_item(
            category=kp.ItemCategory.KEYWORD,
            label="Git: Rescan for Git Repositories",
            short_desc="Rescans the configured paths for git repositories",
            target=self.COMMAND_RESCAN,
            args_hint=kp.ItemArgsHint.FORBIDDEN,
            hit_hint=kp.ItemHitHint.KEEPALL,
        ))
        catalog.append(self.create_item(
            category=kp.ItemCategory.KEYWORD,
            label="Git: Remove not existing Git Repositories",
            short_desc="Removes not existing Git Repositories",
            target=self.COMMAND_REMOVE_OLD,
            args_hint=kp.ItemArgsHint.FORBIDDEN,
            hit_hint=kp.ItemHitHint.KEEPALL,
        ))
        catalog.append(self.create_item(
            category=kp.ItemCategory.KEYWORD,
            label="Git: Run garbage collection on all Git Repositories",
            short_desc="Run garbage collection on all Git Repositories if it's needed",
            target=self.COMMAND_GARBAGE_COLLECTION_ALL,
            args_hint=kp.ItemArgsHint.FORBIDDEN,
            hit_hint=kp.ItemHitHint.KEEPALL,
        ))
        for cmd in self._cmds_all:
            item = self.create_item(
                category=kp.ItemCategory.KEYWORD,
                label=cmd.label,
                short_desc='Run "{} {}" on all Git Repositories'.format(cmd.cmd, cmd.args),
                target=self.COMMAND_CMD_ALL + cmd.name,
                args_hint=kp.ItemArgsHint.FORBIDDEN,
                hit_hint=kp.ItemHitHint.IGNORE,
                data_bag=repr(cmd)
            )
            catalog.append(item)

        catalog.extend(self._create_repo_items())

        self.set_catalog(catalog)

    def _create_repo_items(self):
        items = []
        for git_repo in self._git_repos:
            # self.dbg(git_repo)
            items.append(self.create_item(
                category=kp.ItemCategory.KEYWORD,
                label='Git: Repository "{}"'.format(git_repo.name),
                short_desc=git_repo.path,
                target=git_repo.path,
                args_hint=kp.ItemArgsHint.REQUIRED,
                hit_hint=kp.ItemHitHint.NOARGS,
                data_bag=git_repo.name
            ))
        return items

    def on_suggest(self, user_input, items_chain):
        if not items_chain:
            return

        suggestions = []

        if len(items_chain) > 1:
            rename_item = items_chain[1].clone()
            rename_item.set_short_desc('{} "{}" to "{}"'.format(rename_item.label(), items_chain[0].data_bag(), user_input))
            rename_item.set_label('{} "{}"'.format(rename_item.label(), items_chain[0].data_bag()))
            rename_item.set_args(user_input)
            suggestions.append(rename_item)
            self.set_suggestions(suggestions)
            return

        if self._git_bash_path and os.path.exists(self._git_bash_path):
            open_git_bash = self.create_item(
                category=kp.ItemCategory.KEYWORD,
                label="Open Git-Bash",
                short_desc=self._git_bash_path,
                target=self.COMMAND_OPEN_GIT_BASH,
                args_hint=kp.ItemArgsHint.REQUIRED,
                hit_hint=kp.ItemHitHint.IGNORE,
            )
            open_git_bash.set_args(items_chain[0].target())
            suggestions.append(open_git_bash)

        open_explorer = self.create_item(
            category=kp.ItemCategory.KEYWORD,
            label="Open Explorer",
            short_desc="explorer.exe",
            target="explorer.exe",
            args_hint=kp.ItemArgsHint.REQUIRED,
            hit_hint=kp.ItemHitHint.IGNORE,
            icon_handle=self.load_icon("@{},0".format("explorer.exe"))
        )
        open_explorer.set_args('"{}"'.format(items_chain[0].target()))
        suggestions.append(open_explorer)

        rename_repo = self.create_item(
            category=kp.ItemCategory.KEYWORD,
            label="Rename Repository",
            short_desc="Rename the name of the repository in keypirinha",
            target=self.COMMAND_RENAME,
            args_hint=kp.ItemArgsHint.REQUIRED,
            hit_hint=kp.ItemHitHint.IGNORE,
            data_bag=items_chain[0].target()
        )
        suggestions.append(rename_repo)

        for command in self._cmds:
            command_item = self.create_item(
                category=kp.ItemCategory.KEYWORD,
                label=command.label,
                short_desc=command.cmd,
                target=command.cmd,
                args_hint=kp.ItemArgsHint.REQUIRED,
                hit_hint=kp.ItemHitHint.IGNORE,
                icon_handle=self.load_icon("@{},0".format(command.cmd)) if os.path.isabs(command.cmd) else None,
                data_bag=command.cwd.format(repo_path=items_chain[0].target()) if command.cwd else None
            )
            command_item.set_args(command.args.format(repo_path=items_chain[0].target()))
            suggestions.append(command_item)

        open_git_bash = self.create_item(
            category=kp.ItemCategory.KEYWORD,
            label="Run garbage collection",
            short_desc='Runs "git gc"',
            target=self.COMMAND_GARBAGE_COLLECTION,
            args_hint=kp.ItemArgsHint.REQUIRED,
            hit_hint=kp.ItemHitHint.IGNORE,
        )
        open_git_bash.set_args(items_chain[0].target())
        suggestions.append(open_git_bash)

        self.set_suggestions(suggestions)

    def on_execute(self, item, action):
        self.dbg("on_execute", item.target(), item.raw_args(), item.data_bag())

        if item.target() == self.COMMAND_RESCAN:
            self._rescan()
            self.on_catalog()
        elif item.target() == self.COMMAND_OPEN_GIT_BASH:
            kpu.shell_execute(self._git_bash_path, working_dir=item.raw_args())
        elif item.target() == self.COMMAND_GARBAGE_COLLECTION:
            self._run_gc(item.raw_args())
        elif item.target() == self.COMMAND_GARBAGE_COLLECTION_ALL:
            for repo in self._git_repos:
                self._run_gc(repo.path)
        elif item.target() == self.COMMAND_REMOVE_OLD:
            remove_repos = []
            for repo in self._git_repos:
                if not os.path.exists(repo.path):
                    remove_repos.append(repo)
            self.dbg(remove_repos)
            for repo in remove_repos:
                self._git_repos.remove(repo)
            self._save_repos()
        elif item.target() == self.COMMAND_RENAME:
            new_name = item.raw_args()
            repo_path = item.data_bag()
            for repo in self._git_repos:
                if repo.path == repo_path:
                    self.info("renaming", repo.name, "to", new_name, repo_path)
                    repo.name = new_name
                    break
            self._save_repos()
            self.on_catalog()
        elif item.target().startswith(self.COMMAND_CMD_ALL):
            cmd = eval(item.data_bag())
            self.dbg(cmd)
            command = cmd.cmd + " " + cmd.args
            for repo in self._git_repos:
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                self.info("running", command, "in", repo.path)
                proc = subprocess.run(command, cwd=repo.path, stdout=subprocess.PIPE, stderr=subprocess.PIPE, startupinfo=startupinfo)
                self.info(command, "returned", proc.returncode)
                if proc.stdout:
                    self.info(proc.stdout.decode())
                if proc.stderr:
                    self.warn(proc.stderr.decode())
        else:
            self.dbg("running", item.target(), item.raw_args())
            cwd = item.data_bag()
            self.dbg(cwd)
            if cwd:
                kpu.shell_execute(item.target(), item.raw_args(), working_dir=cwd)
            else:
                kpu.shell_execute(item.target(), item.raw_args())

    def _run_gc(self, repo):
        command = '"{}" {}'.format(self._git_path, self.ARGS_COUNT_OBJECT)
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        if not os.path.exists(repo):
            self.err(repo, "does not exist")
            return
        if not os.path.isdir(repo):
            self.err(repo, "is not a directory")
            return
        self.dbg("running", command, "in", repo)
        proc = subprocess.run(command, cwd=repo, stdout=subprocess.PIPE, startupinfo=startupinfo)
        if proc.returncode != 0:
            self.warn("command returned", proc.returncode, "for", repo)
            return
        output = os.path.normpath(proc.stdout.decode().rstrip("\r\n"))
        self.dbg(output)
        out_split = output.split()
        loose_kb = 0
        if len(out_split) <= 2:
            return
        loose_kb = int(out_split[2])
        self.dbg("loose_kb", loose_kb)
        if loose_kb < 10:
            self.info("garbage collection not needed")
            return
        command = '"{}" {}'.format(self._git_path, self.ARGS_GC)
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        self.info("running", command, "in", repo)
        proc = subprocess.run(command, cwd=repo, stdout=subprocess.PIPE, startupinfo=startupinfo)
        if proc.returncode != 0:
            self.dbg("command returned", proc.returncode, "for", repo)


class GitRepo(object):
    __slots__ = ("name", "path")

    def __init__(self, name, path):
        self.name = name
        self.path = path

    def __str__(self):
        return "{}, {}".format(self.name, self.path)

    def __repr__(self):
        return "GitRepo(name={}, path={})".format(repr(self.name), repr(self.path))

    def __eq__(self, other):
        return self.path == other.path

    def __lt__(self, other):
        return self.path < other.path

    def __le__(self, other):
        return self.path <= other.path

    def __gt__(self, other):
        return self.path > other.path

    def __ge__(self, other):
        return self.path >= other.path


class GitRepoEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, GitRepo):
            return {"name": o.name, "path": o.path}
        return super().default(o)


class GitRepoDecoder(json.JSONDecoder):
    def __init__(self):
        super().__init__(object_hook=self.dict_to_obj)

    def dict_to_obj(self, decoded):
        if "name" in decoded and "path" in decoded:
            return GitRepo(decoded["name"], decoded["path"])
        return decoded


class GitCommand(object):
    __slots__ = ("name", "label", "cmd", "args", "cwd")

    def __init__(self, name, cmd, label=None, args=None, cwd=None):
        self.name = name
        self.cmd = cmd
        self.label = label
        self.args = args
        self.cwd = cwd

    def __str__(self):
        return "{}, '{} {}'".format(self.label, self.cmd, self.args)

    def __repr__(self):
        return "GitCommand(name={}, label={}, cmd={}, args={}, cwd={})".format(repr(self.name),
                                                                               repr(self.label),
                                                                               repr(self.cmd),
                                                                               repr(self.args),
                                                                               repr(self.cwd))
