address="127.0.0.1"
port=5353
websites=("baidu.com" "github.com" "i.sjtu.edu.cn" "taobao.com")
qtype=("A" "AAAA")

echo Start testing the DNSServer...
for site in "${websites[@]}"; do
    for qt in "${qtype[@]}"; do
        python3 -m dnslib.client --server ${address}:${port} ${site} ${qt}
    done
done