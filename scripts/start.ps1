Set-Location "$PSScriptRoot\.."
docker-compose up -d --build

Write-Host "`n[HOAN TAT] He thong da san sang!" -ForegroundColor Green
Write-Host "- Admin Dashboard: http://localhost:5000/admin"
Write-Host "- Employee Portal: http://localhost:5000/portal"
Write-Host "- Mailpit NV1-NV4: http://localhost:8021 den 8024"