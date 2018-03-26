import requests
from flask import Flask, jsonify, request
import blockchain as bc
import json
import sys
import rsa
import base64
from uuid import uuid4

# Cryptocurrency is just a private key that "allows" access to account
(pub_key, priv_key) = rsa.newkeys(512) 
# Generate a public key unique address for this node
node_identifier = pub_key.save_pkcs1().decode('UTF-8')

#Instantiate the Node
app = Flask(__name__)

# Instantiate the Blockchain
blockchain = bc.Blockchain()


@app.route('/mine', methods=['GET'])
def mine():
    # We run the proof of work algorithm to get the next proof...
    last_block = blockchain.last_block
    last_proof = last_block['proof']
    proof = blockchain.proof_of_work(last_proof)

    # We must receive a reward for finding the proof.
    # The sender is "0" to signify that this node has mined a new coin.
    message = f'0{node_identifier}1'
    signature = rsa.sign(message.encode('UTF-8'),priv_key,'SHA-256')
    blockchain.new_transaction(
        sender="0",
        recipient=node_identifier,
        amount=1,
        signature = base64.b64encode(signature).decode('UTF-8')
    )

    # Forge the new Block by adding it to the chain
    previous_hash = blockchain.hash(last_block)
    block = blockchain.new_block(proof, previous_hash)

    temp = set()
    temp.add(f'{addr}:{portn}')
    temp.update(blockchain.nodes)
    
    broadcast = {
        'nodes': list(temp),
        'block': block
    }
    
    for node in blockchain.nodes:
             requests.post(f'http://{node}/nodes/block/new', json = broadcast)
             
    response = {
        'message': "New Block Forged",
        'index': block['index'],
        'transactions': block['transactions'],
        'proof': block['proof'],
        'previous_hash': block['previous_hash'],
    }
    return jsonify(response), 200

@app.route('/nodes/block/new', methods=['POST'])
def recieve_block():
    values = request.get_json()
    
    required = ['nodes','block']
    if (values is None or not all(k in values for k in required)):
        return 'Missing values', 400
    required = ['index', 'proof', 'previous_hash','timestamp','transactions']
    if (not all(k in values['block'] for k in required)):
        return 'Missing value in block', 400
    
    if (not blockchain.accept_block(values['block']['proof'],values['block']['index'],values['block']['previous_hash'],values['block']['timestamp'],values['block']['transactions'])):
        return 'Invalid block', 400

    diff = blockchain.nodes - set(values['nodes'])
    # find nodes that werent notified of transaction
    values['nodes']= list(blockchain.nodes | set(values['nodes']))
    for node in diff :
        # add new nodes to blockchain
        blockchain.register_node(node)
        requests.post(f'http://{node}/nodes/block/new', json = values)
    

    return 'Block Added', 201

@app.route('/nodes/transactions/new', methods=['POST'])
def new_transaction_internal():
    values = request.get_json()
    
    # Check that required fields are in the POST'ed data

    required = ['nodes', 'transaction']
    if (values is None or not all (k in values for k in required)):
        return 'Missing values', 400
    required = ['sender', 'recipient', 'amount', 'signature']
    if (not all(k in values['transaction'] for k in required)):
        return 'Missing transaction values', 400
    
    if (not blockchain.test_transaction(values)):
        return 'Already have transaction', 200
    
    if (not blockchain.valid_transaction(values['sender'],values['recipient'],values['amount'],values['signature'])):
        return 'Invalid Transaction', 400
    
    diff = blockchain.nodes - set(values['nodes'])
    # find nodes that werent notified of transaction
    values['nodes']= list(blockchain.nodes | set(values['nodes']))
    for node in diff :
        # add new nodes to blockchain
        blockchain.register_node(node)
        requests.post(f'http://{node}/nodes/transactions/new', json = values)
    # Create a new Transaction
    index = blockchain.new_transaction(values['transaction']['sender'],values['transaction']['recipient'],values['transaction']['amount'],values['transaction']['signature'])

    response = {'message': f'Transaction will be added to Block {index}'}
    return jsonify(response), 201
        
        
    
@app.route('/transactions/new', methods=['POST'])
def new_transaction():
    values = request.get_json()
    
    # Check that the required fields are in the POST'ed data
    required = ['sender', 'recipient', 'amount', 'signature']
    if (values is None or not all(k in values for k in required)):
        return 'Missing values', 400
    if (not blockchain.valid_transaction(values['sender'],values['recipient'],values['amount'],values['signature'])):
        return 'Invalid Transaction', 400
    
    # Create a new Transaction
    index = blockchain.new_transaction(values['sender'],values['recipient'],values['amount'],values['signature'])
    temp = set()
    temp.add(f'{addr}:{portn}')
    temp.update(blockchain.nodes)
    # Include nodes broadcasting to so nodes know who it was sent too
    broadcast = {
                  'nodes': list(temp),
                     'transaction': {
                     'sender': values['sender'],
                     'recipient': values['recipient'],
                     'amount': values['amount'],
                     'signature': values['signature']}}
    
    for node in blockchain.nodes:
             requests.post(f'http://{node}/nodes/transactions/new', json = broadcast)
    response = {'message': f'Transaction will be added to Block {index}'}
    return jsonify(response), 201

@app.route('/chain', methods=['GET'])
def full_chain():
    response = {
	'transactions': blockchain.current_transactions,
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
    

    request_body = {
        "nodes" : [f'http://{addr}:{portn}']
    }

    for node in nodes:
        blockchain.register_node(node)
        requests.post(f'{node}/nodes/register', json = request_body)

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

# This will probably be used by the website and mobile
# to turn a ip address into a node identifier
@app.route('/identifier', methods=['GET'])
def identity():
    response = {'address': node_identifier}
    return jsonify(response), 200

portn=0
addr=""
def main(host,port):
    """

    Starts up the server

    :param host: <str> The host address of the server
    :param port: <int> The port that the server is listening too
    """
    portn=port
    addr=host
    app.run(host=host, port=port)
