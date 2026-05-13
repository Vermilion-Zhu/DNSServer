#Testing script for our DNS server, running on Windows
#There is another simple version for Linux...
$address = "127.0.0.1"
$port = 5353

$websites = @("google.com", "jdqmyepcif.com", "github.com", 'i.sjtu.edu.cn', 'qpxmvbxwryt.com', 'zxcvbnmkhg.net', '1a2b3c4d5e6f.org', 'kjhgfdsaoiuy.xyz', 'mvznxbcals.top', 'wpqoeiruty12.ru', 'alspdkfjgh.cc', 'mznxbcv1029.info', 'eqwzjxk.com')
$qtype = @("A", "AAAA", "CNAME")

Write-Host "Start testing the DNSServer..." -ForegroundColor Yellow

for ($i = 1; $i -le 5; $i++){
    foreach ($site in $websites) {
        foreach ($qt in $qtype) {
            Write-Host "Testing $site ($qt)..." -ForegroundColor Cyan

            #Questing the server about the website with different qtypes.
            python -m dnslib.client --server ${address}:${port} $site $qt
            
            if ($LASTEXITCODE -eq 0) {
                Write-Host "Test for $site ($qt) succeeded!" -ForegroundColor Green
            } else {
                Write-Host "Test for $site ($qt) failed!" -ForegroundColor Red
            }
            Write-Host "---"
        }
    }
}

Write-Host "Test complete." -ForegroundColor Yellow
Read-Host "Enter to quit..."