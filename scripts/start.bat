@echo off
chcp 65001 > nul





docker-compose up -d --build


echo - Admin Dashboard: http://localhost:5000/admin
echo - Portal Nhan vien: http://localhost:5000/portal
echo - WebMail Mailpit:  http://localhost:8021


timeout /t 3 > nul
start http://localhost:5000/admin
start http://localhost:5000/portal

