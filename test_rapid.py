from rapidocr import RapidOCR

r = RapidOCR()
print('RapidOCR engine OK')
print([m for m in dir(r) if not m.startswith('_')])
result = r('invoice_test.png')
print('RESULT TYPE:', type(result))
if isinstance(result, tuple):
    res, elapse = result
    print('ITEMS:', len(res) if res else 0)
    if res:
        for item in res[:5]:
            print(item)
