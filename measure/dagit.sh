#!/usr/bin/env bash
# Runs on the Mac and only copies files and starts things: k6 and the contestants run on the rented boxes.
#   dagit.sh uretici  GEN K6_VERSION                     set up a generator and build the seed there
#   dagit.sh hedef    GEN HEDEF HEDEF_OZEL ufw|noufw TIER  set up a target from that generator, keep its box.txt
#   dagit.sh yarismaci GEN HEDEF_OZEL <folder>            install on both, build on the generator, copy
#   dagit.sh kos      GEN HEDEF_OZEL NAME TIER [arama.py flags]  start the search in tmux on the generator
#   dagit.sh cek      GEN                                 pull results to sonuc/
# GEN and HEDEF are public addresses, HEDEF_OZEL is the target's private (VPC) address.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"; KEY="$HERE/.anahtar/v7"
O="-i $KEY -o StrictHostKeyChecking=accept-new -o BatchMode=yes"
on() { local h="$1"; shift; ssh $O "root@$h" "$@"; }
up() { rsync -az --exclude node_modules --exclude seed/notes.db -e "ssh $O" "$@"; }
waitssh() { for _ in $(seq 60); do on "$1" true 2>/dev/null && return 0; sleep 5; done; echo "no ssh on $1"; exit 1; }
case "${1:?command}" in
uretici)
  G="$2"; V="$3"; waitssh "$G"
  on "$G" 'mkdir -p /srv/olcum'
  up "$HERE/uzak" "$HERE/yarisma" "$HERE/arama.py" "$HERE/prob.py" "$HERE/yuk.js" "$HERE/seed.py" "$HERE/gizli_test.py" "$HERE/test_api.py" "$HERE/SPEC.md" "root@$G:/srv/olcum/"
  on "$G" "bash /srv/olcum/uzak/kur-uretici.sh $V && python3 /srv/olcum/seed.py /srv/olcum/seed"
  ;;
hedef)
  G="$2"; H="$3"; P="$4"; FW="$5"; T="$6"; waitssh "$H"
  on "$G" cat /root/.ssh/id_ed25519.pub | on "$H" 'cat >> /root/.ssh/authorized_keys'
  on "$H" 'cloud-init status --wait >/dev/null 2>&1 || true; export DEBIAN_FRONTEND=noninteractive; apt-get -o DPkg::Lock::Timeout=300 update -q; apt-get -o DPkg::Lock::Timeout=300 install -y -q rsync; mkdir -p /root/uzak /srv/seed'
  on "$G" "R='ssh -o StrictHostKeyChecking=accept-new'; cd /srv/olcum && rsync -az -e \"\$R\" uzak/ gizli_test.py test_api.py root@$P:/root/uzak/ && rsync -az -e \"\$R\" seed/notes.db seed/tokens.json root@$P:/srv/seed/"
  on "$H" "bash /root/uzak/kur-hedef.sh $FW"
  mkdir -p "$HERE/sonuc/$T"; on "$H" cat /srv/bench/box.txt > "$HERE/sonuc/$T/box.txt"
  ;;
yarismaci)
  G="$2"; P="$3"; S="${4%/}"; N="$(basename "$S")"
  up "$S/" "root@$G:/srv/yarisma/$N/"
  # every script runs from its own folder, like a CI job would; the prompt did not say where they run
  on "$G" "chown -R deploy:deploy /srv/yarisma/$N && chmod +x /srv/yarisma/$N/*.sh && cd /srv/yarisma/$N && bash install.sh && sudo -u deploy bash -c 'cd /srv/yarisma/$N && bash build.sh' \
    && R='ssh -o StrictHostKeyChecking=accept-new' && rsync -az --delete -e \"\$R\" /srv/yarisma/$N/ root@$P:/srv/yarisma/$N/ \
    && ssh root@$P 'chown -R deploy:deploy /srv/yarisma/$N; cd /srv/yarisma/$N && bash install.sh'"
  ;;
kos)
  G="$2"; P="$3"; N="$4"; T="$5"; shift 5
  on "$G" "tmux new-session -d -s '$T-$N' 'cd /srv/olcum && python3 arama.py --target root@$P --target-ip $P --gen local --name $N --tier $T --out sonuc $* 2>&1 | tee -a kos-$T-$N.log'"
  ;;
cek)
  mkdir -p "$HERE/sonuc"; rsync -az -e "ssh $O" "root@$2:/srv/olcum/sonuc/" "$HERE/sonuc/"
  ;;
*) echo "unknown command"; exit 1;;
esac
