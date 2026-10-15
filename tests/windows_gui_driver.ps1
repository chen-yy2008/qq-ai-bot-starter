param([int]$RootPid,[switch]$NoticeOnly)
$ErrorActionPreference='Stop'
[Console]::InputEncoding=New-Object System.Text.UTF8Encoding($false)
Add-Type -TypeDefinition @'
using System;
using System.Text;
using System.Runtime.InteropServices;
using System.Collections.Generic;
public static class QQLabGuiDriver {
 public delegate bool EnumWindowProc(IntPtr h,IntPtr p);
 [DllImport("user32.dll")] public static extern bool EnumWindows(EnumWindowProc callback,IntPtr p);
 [DllImport("user32.dll")] public static extern bool EnumChildWindows(IntPtr h,EnumWindowProc callback,IntPtr p);
 [DllImport("user32.dll",CharSet=CharSet.Unicode)] public static extern int GetWindowText(IntPtr h,StringBuilder text,int count);
 [DllImport("user32.dll",CharSet=CharSet.Unicode)] public static extern int GetClassName(IntPtr h,StringBuilder text,int count);
 [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h,out uint pid);
 [DllImport("user32.dll",CharSet=CharSet.Unicode)] public static extern IntPtr SendMessage(IntPtr h,uint msg,IntPtr w,string text);
 [DllImport("user32.dll")] public static extern IntPtr SendMessage(IntPtr h,uint msg,IntPtr w,IntPtr l);
 [StructLayout(LayoutKind.Sequential,CharSet=CharSet.Unicode)] public struct Entry {
   public uint size,usage,pid; public IntPtr heap; public uint module,threads,parent; public int priority; public uint flags;
   [MarshalAs(UnmanagedType.ByValTStr,SizeConst=260)] public string exe;
 }
 [DllImport("kernel32.dll")] static extern IntPtr CreateToolhelp32Snapshot(uint flags,uint pid);
 [DllImport("kernel32.dll",CharSet=CharSet.Unicode)] static extern bool Process32FirstW(IntPtr snapshot,ref Entry entry);
 [DllImport("kernel32.dll",CharSet=CharSet.Unicode)] static extern bool Process32NextW(IntPtr snapshot,ref Entry entry);
 [DllImport("kernel32.dll")] static extern bool CloseHandle(IntPtr h);
 public static bool Descendant(uint pid,uint root) {
   var parents=new Dictionary<uint,uint>(); var h=CreateToolhelp32Snapshot(2,0);
   try { var e=new Entry();e.size=(uint)Marshal.SizeOf(typeof(Entry));
     if(Process32FirstW(h,ref e)) do {parents[e.pid]=e.parent;} while(Process32NextW(h,ref e));
   } finally { CloseHandle(h); }
   for(int i=0;i<32 && pid!=0;i++) {if(pid==root)return true;if(!parents.ContainsKey(pid))break;pid=parents[pid];}
   return false;
 }
 public static string Text(IntPtr h) {var b=new StringBuilder(1024);GetWindowText(h,b,b.Capacity);return b.ToString();}
 public static string Class(IntPtr h) {var b=new StringBuilder(256);GetClassName(h,b,b.Capacity);return b.ToString();}
}
'@
try {
    $data=[Console]::In.ReadToEnd() | ConvertFrom-Json
    $deadline=[DateTime]::UtcNow.AddSeconds(300)
    $script:submitted=$false
    while ([DateTime]::UtcNow -lt $deadline) {
        $script:handled=$false
        $callback=[QQLabGuiDriver+EnumWindowProc]{
            param($window,$unused)
            [uint32]$windowPid=0
            [void][QQLabGuiDriver]::GetWindowThreadProcessId($window,[ref]$windowPid)
            if (![QQLabGuiDriver]::Descendant($windowPid,[uint32]$RootPid)) { return $true }
            $title=[QQLabGuiDriver]::Text($window)
            if ($title -notlike 'QQ 毒舌群友*') { return $true }
            $script:edits=New-Object 'System.Collections.Generic.List[System.IntPtr]'
            $script:buttons=New-Object 'System.Collections.Generic.List[System.IntPtr]'
            $child=[QQLabGuiDriver+EnumWindowProc]{
                param($handle,$p)
                $class=[QQLabGuiDriver]::Class($handle)
                if ($class -like 'WindowsForms10.EDIT*') { $script:edits.Add($handle) }
                if ($class -like '*BUTTON*' -or $class -eq 'Button') { $script:buttons.Add($handle) }
                return $true
            }
            [void][QQLabGuiDriver]::EnumChildWindows($window,$child,[IntPtr]::Zero)
            if (!$NoticeOnly -and !$script:submitted -and $script:edits.Count -eq 2) {
                foreach ($edit in $script:edits) { [void][QQLabGuiDriver]::SendMessage($edit,12,[IntPtr]::Zero,[string]$data.password) }
                foreach ($button in $script:buttons) {
                    if ([QQLabGuiDriver]::Text($button) -eq '保存密码') {
                        [void][QQLabGuiDriver]::SendMessage($button,245,[IntPtr]::Zero,[IntPtr]::Zero)
                        $script:submitted=$true
                        [Console]::WriteLine('PASSWORD_FORM_SUBMITTED')
                        break
                    }
                }
            } elseif (($NoticeOnly -or $script:submitted) -and $title -eq 'QQ 毒舌群友' -and $script:buttons.Count -gt 0) {
                [void][QQLabGuiDriver]::SendMessage($script:buttons[0],245,[IntPtr]::Zero,[IntPtr]::Zero)
                $script:handled=$true
                [Console]::WriteLine('NOTICE_DISMISSED')
            }
            return $true
        }
        [void][QQLabGuiDriver]::EnumWindows($callback,[IntPtr]::Zero)
        if ($script:handled) { [Console]::Write('GUI_COMPLETED'); exit 0 }
        Start-Sleep -Milliseconds 150
    }
    exit 2
} catch { [Console]::Error.WriteLine('GUI_AUTOMATION_FAILED'); exit 1 }
