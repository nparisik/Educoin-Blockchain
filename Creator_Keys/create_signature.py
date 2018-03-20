import rsa
import sys
import base64

# Hard coding this for now because I was having trouble with command line arguements
rec = '-----BEGIN RSA PUBLIC KEY-----\nMEgCQQCeLGEf8gbgM2L+ojj8Z1oin45HAerscOWswHVV5SFIIArL6YVsjZW4Eg4p\n/1OIWaJbnKc0cLAtOU5YKf1m+RfvAgMBAAE=\n-----END RSA PUBLIC KEY-----\n'

if (len(sys.argv) < 2):
    print("usage: python create_signature.py <amount>")
    sys.exit()

priv_key = open("priv_key","r")
priv = rsa.PrivateKey.load_pkcs1(priv_key.read())
priv_key.close()

pub = rsa.PublicKey(priv.n,priv.e).save_pkcs1().decode('UTF-8')

message = f'{pub}{rec}{sys.argv[1]}'
signature = rsa.sign(message.encode('UTF-8'),priv,'SHA-256')
print(f'message:\n{message}')
sig = base64.b64encode(signature).decode('UTF-8')
print(f'signature:\n{sig}')
rsa.verify(message.encode('UTF-8'),signature,rsa.PublicKey(priv.n,priv.e))

