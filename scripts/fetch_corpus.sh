#!/usr/bin/env bash
# Reproducible test corpus. Downloads real public documents into corpus/real/.
# Synthetic ground-truth samples are generated separately: python scripts/make_samples.py
set -u
cd "$(dirname "$0")/.."
UA="transdoc-research/0.1 (https://github.com/muhammadmishbakhuzzuhail/translate)"
mkdir -p corpus/real/{full_image,digital_text,scanned_pdf,multilingual,forms}

dl(){ # url out match
  curl -sL -A "$UA" --max-time 120 -o "$2" "$1"
  sz=$(stat -c%s "$2" 2>/dev/null || echo 0); ct=$(file -b "$2" 2>/dev/null)
  if [ "$sz" -gt 3000 ] && echo "$ct" | grep -qiE "$3"; then
    echo "OK   ${2#corpus/real/} ($sz B)"
  else
    echo "FAIL ${2#corpus/real/} ($sz) $ct"; rm -f "$2"
  fi
}

echo "== digital_text =="
dl "https://arxiv.org/pdf/1706.03762" corpus/real/digital_text/arxiv_attention_en.pdf pdf
dl "https://arxiv.org/pdf/1810.04805" corpus/real/digital_text/arxiv_bert_en.pdf pdf

echo "== forms =="
dl "https://www.irs.gov/pub/irs-pdf/fw9.pdf"  corpus/real/forms/irs_w9_form.pdf pdf
dl "https://www.irs.gov/pub/irs-pdf/f1040.pdf" corpus/real/forms/irs_1040_form.pdf pdf

echo "== multilingual (born-digital, UDHR) =="
B="https://www.ohchr.org/sites/default/files/UDHR/Documents/UDHR_Translations"
for c in eng:english chn:chinese rus:russian jpn:japanese kkn:korean; do
  dl "$B/${c%%:*}.pdf" corpus/real/multilingual/udhr_${c##*:}.pdf pdf
done
dl "https://ar.wikipedia.org/api/rest_v1/page/pdf/%D8%A7%D9%84%D8%A5%D8%B9%D9%84%D8%A7%D9%86_%D8%A7%D9%84%D8%B9%D8%A7%D9%84%D9%85%D9%8A_%D9%84%D8%AD%D9%82%D9%88%D9%82_%D8%A7%D9%84%D8%A5%D9%86%D8%B3%D8%A7%D9%86" corpus/real/multilingual/udhr_arabic.pdf pdf

echo "== scanned_pdf (real machine scans, no text layer) =="
dl "$B/hnd.pdf" corpus/real/scanned_pdf/udhr_hindi_scan.pdf pdf
dl "$B/thj.pdf" corpus/real/scanned_pdf/udhr_thai_scan.pdf pdf

echo "== full_image (document as image) =="
dl "https://commons.wikimedia.org/wiki/Special:FilePath/Constitution_of_the_United_States,_page_1.jpg?width=2000" corpus/real/full_image/us_constitution_p1.jpg image
dl "https://commons.wikimedia.org/wiki/Special:FilePath/Magna_Carta_(British_Library_Cotton_MS_Augustus_II.106).jpg?width=1800" corpus/real/full_image/magna_carta_la.jpg image
dl "https://upload.wikimedia.org/wikipedia/commons/0/07/Diamond_sutra.jpg" corpus/real/full_image/diamond_sutra_zh.jpg image
# Commons-search-resolved images (Arabic manuscript, Chinese doc, handwriting, etc.)
python scripts/fetch_commons_images.py 2>/dev/null || echo "  (run scripts/fetch_commons_images.py for script-diverse images)"

echo "done."
