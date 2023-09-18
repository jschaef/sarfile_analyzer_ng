#!/usr/bin/python
# -*- coding: UTF8 -*-
#
# Author: Jochen Schäfer <jochen.schaefer@suse.com, 2001-2021
# GNU Public Licence
#
# hashing.py	12 Okt 2020
# https://www.vitoshacademy.com/hashing-passwords-in-python/
from hashlib import sha256, pbkdf2_hmac
from binascii import hexlify
from os import urandom
 
def hash_password(password):
    """Hash a password for storing."""
    salt = sha256(urandom(60)).hexdigest().encode('ascii')
    pwdhash = pbkdf2_hmac('sha512', password.encode('utf-8'), 
                                salt, 100000)
    pwdhash = hexlify(pwdhash)
    return (salt + pwdhash).decode('ascii')
 
def verify_password(stored_password, provided_password):
    """Verify a stored password against one provided by user"""
    salt = stored_password[:64]
    stored_password = stored_password[64:]
    pwdhash = pbkdf2_hmac('sha512', 
                                  provided_password.encode('utf-8'), 
                                  salt.encode('ascii'), 
                                  100000)
    pwdhash = hexlify(pwdhash).decode('ascii')
    return pwdhash == stored_password

if __name__ == "__main__":
    print('Hashing password linux')
    pwd = hash_password("linux")
    print(pwd)
    print("Verify password")
    ret = verify_password(pwd, 'linux')
    print(ret)
