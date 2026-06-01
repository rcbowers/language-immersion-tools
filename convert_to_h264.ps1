param(
    [string]$Dir = ".",
    [int]$Crf = 22,
    [string]$Preset = "fast"
)

$files = Get-ChildItem "$Dir\*.mp4" | Where-Object { $_.Name -notlike "*.h264tmp.mp4" }
$total = $files.Count
$converted = 0
$skipped = 0
$failed = 0

Write-Host ""
Write-Host "AV1 -> H.264 Converter" -ForegroundColor Cyan
Write-Host "$Dir" -ForegroundColor DarkGray
Write-Host "$total files | CRF $Crf | preset $Preset" -ForegroundColor DarkGray
Write-Host ("-" * 60) -ForegroundColor DarkGray
Write-Host ""

$i = 0
foreach ($file in $files) {
    $i++
    $codec = & ffprobe -v quiet -select_streams v:0 -show_entries stream=codec_name -of csv=p=0 $file.FullName 2>&1

    if ($codec -ne "av1") {
        Write-Host "[$i/$total] SKIP  $($file.Name)  ($codec)" -ForegroundColor DarkGray
        $skipped++
        continue
    }

    Write-Host "[$i/$total] CONVERTING  $($file.Name)" -ForegroundColor Yellow
    Write-Host "        -> H.264 CRF=$Crf preset=$Preset" -ForegroundColor DarkGray

    $temp = "$($file.FullName).h264tmp.mp4"
    & ffmpeg -y -i $file.FullName -c:v libx264 -crf $Crf -preset $Preset -c:a copy $temp

    if ($LASTEXITCODE -eq 0) {
        Remove-Item $file.FullName
        Rename-Item $temp $file.Name
        Write-Host "        OK" -ForegroundColor Green
        $converted++
    } else {
        Write-Host "        FAILED" -ForegroundColor Red
        if (Test-Path $temp) { Remove-Item $temp }
        $failed++
    }
    Write-Host ""
}

Write-Host ("-" * 60) -ForegroundColor DarkGray
Write-Host "Done: $converted converted  |  $skipped skipped  |  $failed failed" -ForegroundColor Cyan
Write-Host ""
