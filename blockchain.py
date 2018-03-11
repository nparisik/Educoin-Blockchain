#Source: https://hackernoon.com/learn-blockchains-by-building-one-117428612f46
import hashlib
import json
import sys
from urllib.parse import urlparse
from textwrap import dedent
from time import time
from uuid import uuid4
import requests
from flask import Flask, jsonify, request

if (len(sys.argv) < 3):
    print ("usage: python blockchain.py <host-address> <port>")
    sys.exit()

portn=int(sys.argv[2])
addr = sys.argv[1]

class Blockchain(object):
    def __init__(self):
        self.chain = []
        self.current_transactions = []
        self.nodes=set()
        self.transaction_ids=set()

        #Create the genesis block
        self.new_block(previous_hash=1,proof=100)

    def new_block(self, proof, previous_hash=None):
        """
        Create a new Block in the Blockchain
        
        :param proof: <int> The proof given by the Proof of Work algorithim
        :param previous_hash: (Optional) <str> Hash of previous Block
        :return: <dict> New Block
        """

        block = {
            'index': len(self.chain) +1,
            'timestamp': time(),
            'transactions': self.current_transactions,
            'proof': proof,
            "previous_hash": previous_hash or self.hash(self.chain[-1])
        }
        
        #Reset the current list of transactions
        self.current_transactions = []

        self.chain.append(block)
        return block

    def register_node(self, address):
        """
        Add a new node to the list of nodes
        
        :param address: <str> Address of node. Eg.'http://192.168.0.5:5000'
        :return: None
        """

        parsed_url = urlparse(address)
        self.nodes.add(parsed_url.netloc)

    def valid_chain(self,chain):
        """
        Determine if a given blockchain is valid

        :param chain: <list> A blockchain
        :return: <bool> True if valid, False if not
        """
        last_block = chain[0]
        current_index = 1

        while current_index < len(chain):
            block = chain[current_index]
            print(f'{last_block}')
            print(f'{block}')
            print("\n-----------\n")
            # Check that the hash of the block is correct
            if block['previous_hash'] != self.hash(last_block):
                return False

            # Check that the Proof of Work is correct
            if not self.valid_proof(last_block['proof'], block['proof']):
                return False

            last_block = block
            current_index += 1

        return True

    def resolve_conflicts(self):
        """
        This is our Consensus Algorithm, it resolves conflicts
        by replacing our chain with the longest one in the network.
        
        :return: <bool> True if our chain was replaced, False if not
        """

        neighbours = self.nodes
        new_chain = None

        # We're only looking for chains longer than ours
        max_length = len(self.chain)

        # Grab and verify the chains from all the nodes in our network
        for node in neighbours:
            response = requests.get(f'http://{node}/chain')

            if response.status_code == 200:
                length = response.json()['length']
                chain = response.json()['chain']

                # Check if the length is longer and the chain is valid
                if length > max_length and self.valid_chain(chain):
                    max_length = length
                    new_chain = chain

        # Replace our chain if we discovered a new, valid chain longer than ours
        if new_chain:
            self.chain = new_chain
            return True
        
        return False
    def new_transaction(self, sender, recipient, amount):
        """
        Creates a new transaction to go into the next mined Block
        
        :param sender: <str> Address of the Sender
        :param recipient: <str> Address of the Recipient
        :param amount: <int> Amount
        :return: <int> The index of the Block that will hold this transaction
        """
        self.current_transactions.append({
            'sender': sender,
            'recipient': recipient,
            'amount': amount
        })

        return self.last_block['index'] + 1

    def new_transaction_id(self, id):
        """
        Adds a new transaction Id so that the same transaction cant be added twice
        :param id: <str> Id of the transaction
        :return: <bool> Whether the transaction was already known
        """
        if (id in self.transaction_ids):
            return False
        self.transaction_ids.add(id)
        return True

    @property
    def last_block(self):
        return self.chain[-1]

    
    @staticmethod
    def hash(block):
        """
        Creates a SHA-256 hash of a Block

        :param block: <dict> Block
        :return: <str>
        """
        # We must make sure that the Dictionary is Ordered, or we'll have inconsistent hashes
        block_string = json.dumps(block, sort_keys=True).encode()
        return hashlib.sha256(block_string).hexdigest()


    def proof_of_work(self,last_proof):
        """
        Simple Proof of Work Algorithm:
        - Find a number p' such that hash(pp') contains leading 4 zeroes, where p is the previous p'
        -p is the previous proof, and p' is the new proof

        :param last_proof: <int>
        :return: <int>
        """

        proof = 0
        while self.valid_proof(last_proof, proof) is False:
            proof +=1

        return proof

    @staticmethod
    def valid_proof(last_proof, proof):
        """
        Validates the Proof: Does hash(last_proof, proof) contain 4 leading zeros?
        
        :param last_proof: <int> Previous Proof
        :param proof: <int> Current Proof
        :return: <bool> True if correct, False if not.
        """

        guess = f'{last_proof}{proof}'.encode()
        guess_hash = hashlib.sha256(guess).hexdigest()
        return guess_hash[:4] =="0000"

# Instantiate our Node
app = Flask(__name__)

# Generate a globally unique address for this node
node_identifier = str(uuid4()).replace('-','')


# Instantiate the Blockchain
blockchain = Blockchain()


@app.route('/mine', methods=['GET'])
def mine():
    # We run the proof of work algorithm to get the next proof...
    last_block = blockchain.last_block
    last_proof = last_block['proof']
    proof = blockchain.proof_of_work(last_proof)

    # We must receive a reward for finding the proof.
    # The sender is "0" to signify that this node has mined a new coin.
    blockchain.new_transaction(
        sender="0",
        recipient=node_identifier,
        amount=1,
    )

    # Forge the new Block by adding it to the chain
    previous_hash = blockchain.hash(last_block)
    block = blockchain.new_block(proof, previous_hash)

    response = {
        'message': "New Block Forged",
        'index': block['index'],
        'transactions': block['transactions'],
        'proof': block['proof'],
        'previous_hash': block['previous_hash'],
    }
    return jsonify(response), 200

# TODO: lock this function so only 1 request allowed at a time
@app.route('/nodes/transactions/new', methods=['POST'])
def new_transaction_internal():
    values = request.get_json()
    
    # Check that required fields are in the POST'ed data

    required = ['id','nodes', 'transaction']
    if (values is None or not all (k in values for k in required)):
        return 'Missing values', 400
    required = ['sender', 'recipient', 'amount']
    if (values is None or not all(k in values['transaction'] for k in required)):
        return 'Missing transaction values', 400
    netloc = f'{addr}:{portn}'
    
    if (not blockchain.new_transaction_id(values['id'])):
        return 'Already have transaction', 200
    
    diff = blockchain.nodes - set(values['nodes'])
    # add new nodes to blockchain
    values['nodes']= list(blockchain.nodes | set(values['nodes']))
    for node in diff :
        blockchain.register_node(node)
        requests.post(f'http://{node}/nodes/transactions/new', json = values)
    # Create a new Transaction
    index = blockchain.new_transaction(values['transaction']['sender'],values['transaction']['recipient'],values['transaction']['amount'])
    
    response = {'message': f'Transaction will be added to Block {index}'}
    return jsonify(response), 201
        
        
    
@app.route('/transactions/new', methods=['POST'])
def new_transaction():
    values = request.get_json()
    
    # Check that the required fields are in the POST'ed data
    required = ['sender', 'recipient', 'amount']
    if (values is None or not all(k in values for k in required)):
        return 'Missing values', 400

    # Create a new Transaction
    index = blockchain.new_transaction(values['sender'],values['recipient'],values['amount'])
    temp = set()
    temp.add(f'{addr}:{portn}')
    temp.update(blockchain.nodes)
    # Include nodes broadcasting to so nodes know who it was sent too
    broadcast = {'id': str(uuid4()),
                 'nodes': list(temp),
                 'transaction': {
                     'sender': values['sender'],
                     'recipient': values['recipient'],
                     'amount': values['amount']}}
    
    for node in blockchain.nodes:
             requests.post(f'http://{node}/nodes/transactions/new', json = broadcast)
    response = {'message': f'Transaction will be added to Block {index}'}
    return jsonify(response), 201

@app.route('/chain', methods=['GET'])
def full_chain():
    response = {
        'chain': blockchain.chain,
        'length': len(blockchain.chain)
    }
    return jsonify(response), 200

@app.route('/nodes/register', methods=['POST'])
def register_nodes():
    values = request.get_json()
    if values is None:
        return "Error: Please provide some json",400
    nodes = values.get('nodes')
    if nodes is None:
        return "Error: Please supply a valid list of nodes", 400

    for node in nodes:
        blockchain.register_node(node)

    response = {
        'message': 'New nodes have been added',
        'total_nodes': list(blockchain.nodes),
    }
    return jsonify(response), 201


@app.route('/nodes/resolve', methods=['GET'])
def consensus():
    replaced = blockchain.resolve_conflicts()

    if replaced:
        response = {
            'message': 'Our chain was replaced',
            'new_chain': blockchain.chain
        }
    else:
        response = {
            'message': 'Our chain is authoritative',
            'chain': blockchain.chain
        }

    return jsonify(response), 200

if __name__ == '__main__':
    app.run(host=addr, port=portn)
