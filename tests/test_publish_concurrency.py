import subprocess
import pytest
from run_broadcast import push_completed_episode


def git(root, *args):
    return subprocess.run(['git', '-C', str(root), *args], check=True, capture_output=True, text=True)


def setup_repos(tmp_path):
    remote = tmp_path/'origin.git'
    subprocess.run(['git','init','--bare',str(remote)], check=True, capture_output=True)
    a, b = tmp_path/'producer', tmp_path/'editor'
    subprocess.run(['git','clone',str(remote),str(a)], check=True, capture_output=True)
    git(a,'checkout','-b','main')
    git(a,'config','user.name','Test'); git(a,'config','user.email','test@example.invalid')
    (a/'base.txt').write_text('original')
    git(a,'add','.');git(a,'commit','-m','base');git(a,'push','origin','main')
    subprocess.run(['git','clone','-b','main',str(remote),str(b)],check=True,capture_output=True)
    git(b,'config','user.name','Test');git(b,'config','user.email','test@example.invalid')
    return a,b


def test_remote_editor_change_preserves_paid_master(tmp_path, monkeypatch):
    a,b=setup_repos(tmp_path)
    (a/'episode.mp3').write_bytes(b'completed paid master')
    git(a,'add','.');git(a,'commit','-m','episode')
    (b/'editor.md').write_text('new notes')
    git(b,'add','.');git(b,'commit','-m','editor');git(b,'push','origin','main')
    monkeypatch.chdir(a)
    push_completed_episode('main')
    assert (a/'episode.mp3').read_bytes()==b'completed paid master'
    assert (a/'editor.md').read_text()=='new notes'
    assert git(a,'rev-parse','HEAD').stdout==git(a,'rev-parse','origin/main').stdout


def test_conflicting_edit_aborts_rebase_and_retains_master(tmp_path, monkeypatch):
    a,b=setup_repos(tmp_path)
    (a/'base.txt').write_text('producer version')
    (a/'episode.mp3').write_bytes(b'completed paid master')
    git(a,'add','.');git(a,'commit','-m','episode')
    original=git(a,'rev-parse','HEAD').stdout
    (b/'base.txt').write_text('editor version')
    git(b,'add','.');git(b,'commit','-m','editor');git(b,'push','origin','main')
    monkeypatch.chdir(a)
    with pytest.raises(RuntimeError,match='manual merge'):
        push_completed_episode('main')
    assert git(a,'rev-parse','HEAD').stdout==original
    assert (a/'episode.mp3').read_bytes()==b'completed paid master'
