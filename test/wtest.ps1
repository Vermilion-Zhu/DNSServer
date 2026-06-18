#Testing script for our DNS server, running on Windows
#There is another simple version for Linux...

#Set temporary script execution policy without administrator's authority
#Set-ExecutionPolicy Bypass -Scope Process
$address = "127.0.0.1"
$port = 5353

#$websites = @("google.com", "jdqmyepcif.com", "github.com", 'i.sjtu.edu.cn', 'qpxmvbxwryt.com', 'zxcvbnmkhg.net', '1a2b3c4d5e6f.org', 'kjhgfdsaoiuy.xyz', 'mvznxbcals.top', 'wpqoeiruty12.ru', 'alspdkfjgh.cc', 'mznxbcv1029.info', 'eqwzjxk.com')
#$qtype = @("A", "AAAA", "CNAME")

$websites = @("bytefcdn.com",
    "eu.com",
    "coupang.com",
    "go-mpulse.net",
    "airbnb.com",
    "richaudience.com",
    "samsungosp.com",
    "fidelity.com",
    "state.gov",
    "jimdo.com",
    "azure-devices.net",
    "genius.com",
    "rutube.ru",
    "vercel.app",
    "pccc.com",
    "starlink.com",
    "seedtag.com",
    "epa.gov",
    "webempresa.eu",
    "linode.com",
    "poki.com",
    "upwork.com",
    "ipinfo.io",
    "playrix.com",
    "youku.com",
    "nationalgeographic.com",
    "mailchi.mp",
    "wyzecam.com",
    "agora.io",
    "ubnt.com",
    "character.ai",
    "amazon.com.au",
    "ryanair.com",
    "docker.io",
    "chaturbate.com",
    "eporner.com",
    "pbs.org",
    "typeform.com",
    "repubblica.it",
    "presage.io",
    "kleinanzeigen.de",
    "nintendo.net",
    "btloader.com",
    "readthedocs.io",
    "lowes.com",
    "smilewanted.com",
    "mercadolibre.com.ar",
    "weforum.org",
    "corriere.it",
    "cdnhwc2.com",
    "theatlantic.com",
    "cloudsink.net",
    "usercontent.goog",
    "umich.edu",
    "opera-api.com",
    "xnxx.com",
    "segment.io",
    "rackspace.com",
    "clever.com",
    "hugedomains.com",
    "tsyndicate.com",
    "orderbox-dns.com",
    "px-cloud.net",
    "utorrent.com",
    "4dex.io",
    "whitehouse.gov",
    "jd.com",
    "nextlgsdp.com",
    "nic.io",
    "kwai.com",
    "tawk.to",
    "yandex.com.tr",
    "note.com",
    "caixa.gov.br",
    "tiktokrow-cdn.com",
    "leiniao.com",
    "fbpigeon.com",
    "elmundo.es",
    "onet.pl",
    "theconversation.com",
    "digitaloceanspaces.com",
    "hotstar.com",
    "costco.com",
    "kslawin.com",
    "nexusmods.com",
    "kueezrtb.com",
    "binance.com",
    "afafb.com",
    "xerox.com",
    "ipify.org",
    "kickstarter.com",
    "pixiv.net",
    "onesignal.com",
    "columbia.edu",
    "netgear.com",
    "immedia-semi.com",
    "samsungcloudsolution.net",
    "vk-analytics.ru",
    "spamhaus.org",
    "faphouse.com",
    "snapkit.com",
    "youronlinechoices.com")

$qtype = @("A")

Write-Host "Start testing the DNSServer..." -ForegroundColor Yellow

for ($i = 1; $i -le 10; $i++){
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