#Source: https://hackernoon.com/learn-blockchains-by-building-one-117428612f46
import hashlib
from urllib.parse import urlparse
from textwrap import dedent
from time import time
from threading import Lock
import rsa
import base64
import json
import requests

# TODO implement creator public key
pub_key = open("Creator_Keys/pub_key","r")
CREATOR_KEY= rsa.PublicKey.load_pkcs1(pub_key.read())
pub_key.close()

class Blockchain(object):
    def __init__(self):
        self.chain = []
        self.current_transactions = []
        self.nodes=set()
        self.amount = 0
        self.unspent = {}
        #Used for validating incoming transactions, later updating unspent
        self.temp_unspent = {}

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

        #Update unspent w/ temporary unspent dictionary
        self.unspent.update(self.temp_unspent)

        self.chain.append(block)
        return block
    
    def accept_block(self, proof, index, previous_hash, timestamp, transactions):
        """
        Accepting a Block in the Blockchain
        
        :param proof: <int> The proof given by the Proof of Work algorithim
        :param index: <int> Index of block in blockchain at remote node
        :param previous_hash: <int> Hash of the previous block at remote node
        :param timestamp: <str> Time block was created
        :param transactions: List of transactions
        
        :return: <bool> whether block was accepted or not
        """
        if(len(self.chain) + 1 != index):
            return False

        if(self.last_block['timestamp'] > timestamp):
            return False
        
        if(self.hash(self.last_block) != previous_hash):
            return False
        
        if(not self.valid_proof(self.last_block['proof'], proof)):
            return False
        
        self.temp_unspent.clear()
        self.temp_unspent.update(self.unspent)
        
        for t in transactions:
            if (not self.valid_transaction(t['sender'], t['recipient'], t['amount'], t['signature'])):
                return False
        self.unspent.update(self.temp_unspent)
            
        
        block = {
            'index': index,
            'timestamp': timestamp,
            'transactions': transactions,
            'proof': proof,
            "previous_hash": previous_hash
        }
        # TODO: filter out transactions from current_transactions
        temp = []
        for t in self.current_transactions:
            not_in_trans = True
            for s in transactions:
                if t['sender'] == s['sender'] and t['recipient'] == s['recipient'] and t['amount'] == s['amount']:
                   not_in_trans = False 
            if not_in_trans:
                temp.append(t)
        self.current_transactions = temp

        self.chain.append(block)
        return True
    
    
    def register_node(self, address):
        """
        Add a new node to the list of nodes
        
        :param address: <str> Address of node. Eg.'http://192.168.0.5:5000'
        :return: None
        """

        parsed_url = urlparse(address)
        self.nodes.add(parsed_url.netloc)

    def valid_chain(self,chain,unspent):
        """
        Determine if a given blockchain is valid

        :param chain: <list> A blockchain
        
        :return: <True> new unspent if valid, None if not
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
            
            for t in block['transactions']:
                if (not self.valid_transaction(t['sender'],t['recipient'],t['amount'],t['signature'],unspent=unspent)):
                    return False
                    
            # Check that the Proof of Work is correct
            if not self.valid_proof(last_block['proof'], block['proof']):
                return False

            last_block = block
            current_index += 1

        return True

    def valid_transaction(self,sender,recipient,amount,signature,unspent=None):
        """
        Determine if a transaction is valid
        
        :param sender: <str> The public key of the sender
        :param recipient: <str> The public key of the recipient
        :param amount: <int> The amount of money being sent
        :param signature: <str> The proof of the identity of the node
        :param unspent: <dict> The dict that we are updating
        :return: <bool> True if transaction valid, False if not 
        """

        if (unspent is None):
            unspent = self.temp_unspent
        
        # verify identity of node doing transaction
        try:
            pub = None
            gen = False
            if (sender == "0"):
                gen = True
                pub = rsa.PublicKey.load_pkcs1(recipient)
            else:
                pub = rsa.PublicKey.load_pkcs1(sender)
                
            # double check if destination is valid public key
            rec = rsa.PublicKey.load_pkcs1(recipient)
            message = f'{sender}{recipient}{amount}'
            # convert into byte array 
            sig = base64.b64decode(signature.encode('UTF-8'))
            rsa.verify(message.encode('UTF-8'),sig,pub)
            
            # allow certain key to create money no matter what
            if (pub==CREATOR_KEY or gen):
                tamount = amount if (not sender in unspent.keys()) else amount + unspent[recipient]
                temp = {recipient: tamount}
                unspent.update(temp)
                    
                return True
            # verify if node has enough money to send
            if (sender in unspent.keys() and unspent[sender]<amount):
                return False
            tloss = unspent[sender] - amount
            tamount = amount if (not recipient in unspent.keys()) else amount + unspent[recipient]
            temp = {sender: tloss,recipient: tamount}
            unspent.update(temp)
            
        except:
            return False
        
        return True
    
    def resolve_conflicts(self):
        """
        This is our Consensus Algorithm, it resolves conflicts
        by replacing our chain with the longest one in the network.
        
        :return: <bool> True if our chain was replaced, False if not
        """

        neighbours = self.nodes
        new_chain = None
        new_unspent = {}

        # We're only looking for chains longer than ours
        max_length = len(self.chain)
        current_transactions = []

        # Grab and verify the chains from all the nodes in our network
        for node in neighbours:
            response = requests.get(f'http://{node}/chain')

            if response.status_code == 200:
                length = response.json()['length']
                chain = response.json()['chain']

                unspent = {}
                # Check if the length is longer and the chain is valid
                if length > max_length and self.valid_chain(chain,unspent):
                    new_unspent.clear()
                    new_unspent.update(unspent)
                    max_length = length
                    new_chain = chain
                    current_transactions = response.json()['transactions']

        # Replace our chain if we discovered a new, valid chain longer than ours
        if new_chain:
            self.chain = new_chain
            # add new unspent values that we just calculated
            self.unspent.clear()
            self.temp_unspent.clear()
            self.unspent.update(new_unspent)
            self.temp_unspent.update(new_unspent)
            self.current_transactions = []
            for t in current_transactions:
                if (self.valid_transaction(t['sender'],t['recipient'],t['amount'],t['signature'])):
                    self.new_transaction(t['sender'],t['recipient'],t['amount'],t['signature'])
            return True
        
        return False
    def new_transaction(self, sender, recipient, amount, signature):
        """
        Creates a new transaction to go into the next mined Block
        
        :param sender: <str> Address of the Sender
        :param recipient: <str> Address of the Recipient
        :param amount: <int> Amount
        :param signature: <str> Proof of the Sender
        :return: <int> The index of the Block that will hold this transaction
        """
        self.amount+=amount
        self.current_transactions.append({
            'sender': sender,
            'recipient': recipient,
            'amount': amount,
            'signature': signature
        })

        return self.last_block['index'] + 1

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
   
    def test_transaction(self, last_transaction):
        """
        Takes in transaction id and tests to see if transaction has already occured.

        :param last_transaction: <dict> Previous Transaction
        :return: <bool> True if transaction id is unique, false otherwise
        """
        for t in self.current_transactions:
            if t['sender'] == last_transactions['sender'] and t['recipient'] == last_transactions['recipient'] and t['amount'] == last_transactions['amount']:
                return False
        return True
