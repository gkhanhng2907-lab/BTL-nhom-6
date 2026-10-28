Set-Location "$PSScriptRoot\.."
docker-compose down -v

# Xóa file database cũ nếu tồn tại trong src/
$dbPath = "$PSScriptRoot\..\src\phishing_system.db"
if (Test-Path $dbPath) {
    Remove-Item $dbPath
    Write-Host "Da xoa file database cu: $dbPath" -ForegroundColor Green
}
