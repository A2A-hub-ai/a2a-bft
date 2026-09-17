# -*- coding: utf-8 -*-
"""AutoDL GPU 服务器连接工具（非交互式）。

为什么需要它：``run_on_autodl.sh`` 用的是交互式 ``ssh``，在自动化/非交互环境里
无法输入密码。本工具用 paramiko 完成密码认证，可直接被脚本调用。

**凭据只从环境变量读取，绝不写入任何文件**（本项目曾因明文密码入库而做过一次
凭据清理，见 ``docs/REORGANIZATION_2026-09-15.md`` §3）：

    A2A_SSH_HOST   必填，如 connect.bjb1.seetacloud.com
    A2A_SSH_PORT   必填，如 23965
    A2A_SSH_USER   默认 root
    A2A_SSH_PASS   必填

用法::

    # 执行远端命令（自动打印 stdout/stderr，退出码透传）
    A2A_SSH_HOST=... A2A_SSH_PORT=... A2A_SSH_PASS=... \\
        python experiments/env/ssh_autodl.py "nvidia-smi"

    # 上传 / 下载
    python experiments/env/ssh_autodl.py --put 本地路径 远端路径
    python experiments/env/ssh_autodl.py --get 远端路径 本地路径

    # 远端命令较长时从 stdin 读（bash -s 方式，避免引号地狱）
    echo 'nvidia-smi; ls /autodl-fs/data/models' | python experiments/env/ssh_autodl.py -

    # 把长任务脱离会话跑起来（完成时写 <logfile>.exit）
    python experiments/env/ssh_autodl.py --launch /root/A2A-BFT/exp.log \\
        /root/miniconda3/bin/python experiments/reproduce/reputation_ablation.py --tasks 20

长任务的两个坑（都是踩过的）
--------------------------------------------------------------------------------
1. **别用 ``pkill -f '<关键字>'`` 停长任务。** 远端命令是由
   ``bash -c "cd ... && <关键字> ..."`` 包着执行的，wrapper 自己的命令行里就含
   那串关键字，于是 pkill 会把自己的 SSH 会话一起杀掉——现象是"没有任何输出、
   退出码 127/143"，看起来像命令没执行。改用 ``--launch`` 写的 ``.exit`` 标记 +
   记录 PID。
2. **别用 ``pgrep -f '<关键字>'`` 等长任务结束。** 同理，守望进程自己的命令行里
   也含该关键字，``pgrep`` 永远返回真，循环永不退出。改用轮询 ``<logfile>.exit``。

行尾：本仓库的 ``.sh`` 必须保持 LF（``.gitattributes`` 已强制）。Windows 上编辑过的
脚本传到 Linux 会因 CRLF 报 ``syntax error near unexpected token '$'\\r''`，
上传后用 ``sed -i 's/\\r$//'`` 修一次即可——但正确做法是不要让它进仓库。
"""
import os
import sys

import paramiko


def _conf():
    miss = [k for k in ("A2A_SSH_HOST", "A2A_SSH_PORT", "A2A_SSH_PASS")
            if not os.environ.get(k)]
    if miss:
        sys.exit(f"缺少环境变量: {', '.join(miss)}（密码不要写进文件，用环境变量传入）")
    return (os.environ["A2A_SSH_HOST"], int(os.environ["A2A_SSH_PORT"]),
            os.environ.get("A2A_SSH_USER", "root"), os.environ["A2A_SSH_PASS"])


def connect():
    host, port, user, pw = _conf()
    cli = paramiko.SSHClient()
    cli.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        cli.connect(hostname=host, port=port, username=user, password=pw,
                    timeout=30, banner_timeout=30, auth_timeout=30,
                    look_for_keys=False, allow_agent=False)
    except paramiko.AuthenticationException:
        sys.exit("认证失败：检查 A2A_SSH_PASS / 端口（端口每次开机都可能变）")
    except Exception as e:
        sys.exit(f"连接失败: {type(e).__name__}: {e}")
    return cli


def run(cli, cmd, timeout=None, quiet=False):
    """执行远端命令，返回 (exit_code, 合并输出)。"""
    stdin, stdout, stderr = cli.exec_command(cmd, timeout=timeout, get_pty=False)
    out = stdout.read().decode("utf-8", "replace")
    err = stderr.read().decode("utf-8", "replace")
    rc = stdout.channel.recv_exit_status()
    if not quiet:
        if out:
            print(out, end="" if out.endswith("\n") else "\n")
        if err:
            print(err, end="" if err.endswith("\n") else "\n", file=sys.stderr)
    return rc, out + err


def launch(cli, logfile, cmd):
    """把远端命令**脱离会话**地跑起来，完成时写 `<logfile>.exit` 标记。

    为什么不能直接用 `cmd &` 或 `nohup ... &`：SSH 通道一关，子进程可能被连带
    收掉；而且用 ``pkill -f '<关键字>'`` 去停它会**匹配到 SSH wrapper 自己的
    命令行**（wrapper 的命令行里含同一串关键字），把自己的会话一起杀掉——
    表现为"没有输出、退出码 127/143"。所以：
      - 启动用 ``setsid nohup bash -c '...; echo $? > <logfile>.exit'``
      - 守望用**标记文件**轮询，不要用 ``pgrep -f`` 匹配命令行
      - 停止用标记里记下的 PID，或 ``pkill -f`` 时把关键字写成不会自匹配的形式
    """
    inner = f"{cmd} > {logfile} 2>&1; echo $? > {logfile}.exit"
    rc, _ = run(cli, f"rm -f {logfile}.exit; setsid nohup bash -c {_q(inner)} "
                     f"< /dev/null > /dev/null 2>&1 & echo LAUNCHED", quiet=True)
    if rc == 0:
        print(f"[已启动] 日志: {logfile}   完成标记: {logfile}.exit")
    return rc


def _q(s):
    """单引号包裹并转义内部单引号，供远端 bash 使用。"""
    return "'" + s.replace("'", "'\\''") + "'"


def main():
    args = sys.argv[1:]
    if not args:
        sys.exit(__doc__)

    cli = connect()
    try:
        if args[0] in ("--put", "--get") and len(args) == 3:
            sftp = cli.open_sftp()
            if args[0] == "--put":
                sftp.put(args[1], args[2])
                print(f"[上传] {args[1]} -> {args[2]}")
            else:
                sftp.get(args[1], args[2])
                print(f"[下载] {args[1]} -> {args[2]}")
            sftp.close()
            return 0

        if args[0] == "--launch" and len(args) >= 3:
            return launch(cli, args[1], " ".join(args[2:]))

        cmd = sys.stdin.read() if args[0] == "-" else " ".join(args)
        rc, _ = run(cli, cmd)
        return rc
    finally:
        cli.close()


if __name__ == "__main__":
    sys.exit(main())
