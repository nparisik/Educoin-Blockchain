import sys
import routes

if (len(sys.argv) < 3):
    print ("usage: python main.py <host-address> <port>")
    sys.exit()

portn=int(sys.argv[2])
addr = sys.argv[1]


if __name__ == '__main__':
	routes.main(addr,portn)
