# Keyboard Simulator

这是一个 Windows 下的 Python 键盘模拟程序，直接调用系统 `SendInput` API，不需要安装第三方库。

## 运行条件

- Windows
- Python 3

## 用法

先进入目录：

```powershell
cd "D:\codex\按键program"
```

查看帮助：

```powershell
python .\keyboard_simulator.py --help
```

### 1. 按一次单键

```powershell
python .\keyboard_simulator.py press a
python .\keyboard_simulator.py press enter
python .\keyboard_simulator.py press f5
```

### 2. 连续按多次

```powershell
python .\keyboard_simulator.py press space --repeat 5 --interval 0.2
```

### 3. 发送组合键

```powershell
python .\keyboard_simulator.py hotkey ctrl c
python .\keyboard_simulator.py hotkey ctrl+shift+s
python .\keyboard_simulator.py hotkey alt tab
```

### 4. 输入一段文字

```powershell
python .\keyboard_simulator.py text "hello world"
python .\keyboard_simulator.py text "你好，测试一下"
```

### 5. 按住某个键几秒

```powershell
python .\keyboard_simulator.py hold w --seconds 2
```

### 6. 延迟执行

如果你要先切到别的窗口，可以加延迟：

```powershell
python .\keyboard_simulator.py --delay 3 text "start typing after 3 seconds"
```

## 支持的按键写法

常见命名包括：

- `enter`
- `tab`
- `escape`
- `space`
- `backspace`
- `delete`
- `insert`
- `up` `down` `left` `right`
- `home` `end`
- `pageup` `pagedown`
- `shift` `ctrl` `alt`
- `f1` 到 `f24`
- 单个字符，如 `a`、`1`、`+`

## 注意

- 程序会把按键发送到当前获得焦点的窗口。
- 执行前请先把目标输入框或目标程序切到前台。
- 某些高权限窗口里，如果权限级别不同，模拟输入可能会被系统拦截。这种情况通常需要用相同权限运行终端。
