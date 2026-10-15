param([ValidateSet('setup','reset','notice','selftest')][string]$Mode='setup',[string]$PreviewPath='')
$ErrorActionPreference='Stop'
[Console]::OutputEncoding=New-Object System.Text.UTF8Encoding($false)
[Console]::InputEncoding=New-Object System.Text.UTF8Encoding($false)
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
[System.Windows.Forms.Application]::EnableVisualStyles()
try {
    if ($Mode -eq 'selftest') { $info=@{username='astrbot';address='http://127.0.0.1:6185'} }
    else { $info=[Console]::In.ReadToEnd() | ConvertFrom-Json }
    if ($Mode -eq 'notice') {
        $icon=[System.Windows.Forms.MessageBoxIcon]::Information
        if ($info.error) { $icon=[System.Windows.Forms.MessageBoxIcon]::Warning }
        [void][System.Windows.Forms.MessageBox]::Show([string]$info.message,'QQ 毒舌群友',[System.Windows.Forms.MessageBoxButtons]::OK,$icon)
        exit 0
    }
    if ($Mode -ne 'selftest' -and ![Console]::IsOutputRedirected) { exit 1 }

    $form=New-Object System.Windows.Forms.Form
    $form.Text=if($Mode -eq 'reset'){'QQ 毒舌群友 · 重置管理密码'}else{'QQ 毒舌群友 · 首次设置管理密码'}
    $form.ClientSize=New-Object System.Drawing.Size(620,440)
    $form.StartPosition='CenterScreen'
    $form.FormBorderStyle='FixedDialog'
    $form.MaximizeBox=$false
    $form.MinimizeBox=$false
    $form.Font=New-Object System.Drawing.Font('Microsoft YaHei UI',10)
    $form.AutoScaleMode='Dpi'
    $form.TopMost=$true

    function LabelAt($text,$x,$y,$w,$h) {
        $label=New-Object System.Windows.Forms.Label
        $label.Text=$text; $label.Location=New-Object System.Drawing.Point($x,$y)
        $label.Size=New-Object System.Drawing.Size($w,$h)
        $form.Controls.Add($label)
        return $label
    }
    [void](LabelAt '为本机 AstrBot 面板设置你自己的密码' 28 22 560 30)
    [void](LabelAt '12–128 位，必须包含大写字母、小写字母和数字。' 28 58 560 25)
    [void](LabelAt '默认隐藏；点击每个输入框右侧的小眼睛可显示或隐藏。' 28 87 560 25)
    [void](LabelAt '管理密码' 28 136 110 30)
    [void](LabelAt '再次确认' 28 198 110 30)
    $first=New-Object System.Windows.Forms.TextBox
    $first.Name='ManagementPassword'; $first.AccessibleName='管理密码'
    $first.Location=New-Object System.Drawing.Point(138,132)
    $first.Size=New-Object System.Drawing.Size(390,32)
    $first.MaxLength=128; $first.UseSystemPasswordChar=$true
    $form.Controls.Add($first)
    $second=New-Object System.Windows.Forms.TextBox
    $second.Name='ConfirmManagementPassword'; $second.AccessibleName='再次确认密码'
    $second.Location=New-Object System.Drawing.Point(138,194)
    $second.Size=New-Object System.Drawing.Size(390,32)
    $second.MaxLength=128; $second.UseSystemPasswordChar=$true
    $form.Controls.Add($second)
    $tips=New-Object System.Windows.Forms.ToolTip

    function EyeButton($box,$y,$name) {
        $button=New-Object System.Windows.Forms.Button
        $button.Name=$name; $button.AccessibleName='显示密码'
        $button.Location=New-Object System.Drawing.Point(540,$y)
        $button.Size=New-Object System.Drawing.Size(42,34)
        $button.Tag=$box
        $tips.SetToolTip($button,'显示密码')
        $button.Add_Paint({
            param($sender,$event)
            $pen=New-Object System.Drawing.Pen([System.Drawing.Color]::FromArgb(70,90,110),1.6)
            try {
                $event.Graphics.SmoothingMode='AntiAlias'
                $event.Graphics.DrawEllipse($pen,10,11,20,11)
                $event.Graphics.FillEllipse([System.Drawing.Brushes]::SteelBlue,17,13,7,7)
                if ($sender.Tag.UseSystemPasswordChar) { $event.Graphics.DrawLine($pen,10,25,30,8) }
            } finally { $pen.Dispose() }
        })
        $button.Add_Click({
            param($sender,$event)
            $sender.Tag.UseSystemPasswordChar=!$sender.Tag.UseSystemPasswordChar
            $sender.AccessibleName=if($sender.Tag.UseSystemPasswordChar){'显示密码'}else{'隐藏密码'}
            $tips.SetToolTip($sender,$sender.AccessibleName)
            $sender.Invalidate()
        })
        $form.Controls.Add($button)
        return $button
    }
    $eye1=EyeButton $first 130 'ToggleManagementPassword'
    $eye2=EyeButton $second 192 'ToggleConfirmPassword'
    $errorLabel=LabelAt '' 28 248 560 48
    $errorLabel.ForeColor=[System.Drawing.Color]::Firebrick
    [void](LabelAt ('登录地址：'+$info.address+"`n用户名："+$info.username+'（保留已有用户名）') 28 302 560 46)
    $save=New-Object System.Windows.Forms.Button
    $save.Name='SavePassword'; $save.Text='保存密码'
    $save.Location=New-Object System.Drawing.Point(350,372)
    $save.Size=New-Object System.Drawing.Size(112,38)
    $cancel=New-Object System.Windows.Forms.Button
    $cancel.Text='取消'; $cancel.DialogResult='Cancel'
    $cancel.Location=New-Object System.Drawing.Point(478,372)
    $cancel.Size=New-Object System.Drawing.Size(104,38)
    $form.Controls.AddRange(@($save,$cancel))
    $form.AcceptButton=$save; $form.CancelButton=$cancel
    $save.Add_Click({
        if ($first.Text.Length -lt 12 -or $first.Text.Length -gt 128) { $errorLabel.Text='密码长度应为 12–128 位。'; return }
        if ($first.Text -cnotmatch '[A-Z]' -or $first.Text -cnotmatch '[a-z]' -or $first.Text -notmatch '[0-9]') { $errorLabel.Text='密码需包含大写字母、小写字母和数字。'; return }
        if ($first.Text -cne $second.Text) { $errorLabel.Text='两次输入的密码不一致，请检查。'; return }
        $form.DialogResult='OK'; $form.Close()
    })

    if ($Mode -eq 'selftest') {
        # Exercise the real WinForms controls, without a user password or env bypass.
        $form.Opacity=0; $form.ShowInTaskbar=$false
        $form.Show(); [System.Windows.Forms.Application]::DoEvents()
        if ($PreviewPath) {
            $bitmap=New-Object System.Drawing.Bitmap($form.Width,$form.Height)
            try {
                $rectangle=New-Object System.Drawing.Rectangle(0,0,$form.Width,$form.Height)
                $form.DrawToBitmap($bitmap,$rectangle)
                $bitmap.Save($PreviewPath,[System.Drawing.Imaging.ImageFormat]::Png)
            } finally { $bitmap.Dispose() }
        }
        $first.Text='GuiFixtureA12345'; $second.Text=$first.Text
        if (!$first.UseSystemPasswordChar -or !$second.UseSystemPasswordChar) { throw 'MaskDefault' }
        $eye1.PerformClick()
        if ($first.UseSystemPasswordChar -or !$second.UseSystemPasswordChar) { throw 'Eye1' }
        $eye1.PerformClick(); $eye2.PerformClick()
        if (!$first.UseSystemPasswordChar -or $second.UseSystemPasswordChar) { throw 'Eye2' }
        $eye2.PerformClick()
        $first.Text='short'; $second.Text='short'; $save.PerformClick()
        if (!$errorLabel.Text -or $form.DialogResult -eq 'OK') { throw 'LengthValidation' }
        $first.Text='lowercaseonly123'; $second.Text=$first.Text; $save.PerformClick()
        if ($errorLabel.Text -notlike '*大写*') { throw 'ComplexityValidation' }
        $first.Text='GuiFixtureA12345'; $second.Text='DifferentB12345'; $save.PerformClick()
        if ($errorLabel.Text -notlike '*不一致*') { throw 'ConfirmationValidation' }
        $second.Text=$first.Text; $save.PerformClick()
        if ($form.DialogResult -ne 'OK') { throw 'SaveValidation' }
        $first.Clear(); $second.Clear(); $form.Dispose()
        [Console]::Write('{"controls":"passed","independent_eyes":true,"validation":true}')
        exit 0
    }
    $result=$form.ShowDialog()
    if ($result -ne 'OK') { $first.Clear(); $second.Clear(); $form.Dispose(); exit 2 }
    $payload=@{password=$first.Text;confirmation=$second.Text} | ConvertTo-Json -Compress
    $first.Clear(); $second.Clear(); $form.Dispose()
    [Console]::Write($payload)
    $payload=$null
    exit 0
} catch {
    # Never print exception text, form values, tracebacks or a plaintext password.
    if ($Mode -eq 'selftest') { [Console]::Error.WriteLine('SELFTEST_LINE_'+$_.InvocationInfo.ScriptLineNumber+'_'+$_.Exception.GetType().Name) }
    exit 1
}
