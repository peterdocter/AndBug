#!/usr/bin/env python
# -*- coding: utf-8 -*- 

## Copyright 2011, IOActive, Inc. All rights reserved.
##
## AndBug is free software: you can redistribute it and/or modify it under 
## the terms of version 3 of the GNU Lesser General Public License as 
## published by the Free Software Foundation.
##
## AndBug is distributed in the hope that it will be useful, but WITHOUT ANY
## WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS 
## FOR A PARTICULAR PURPOSE.  See the GNU Lesser General Public License for 
## more details.
##
## You should have received a copy of the GNU Lesser General Public License
## along with AndBug.  If not, see <http://www.gnu.org/licenses/>.

'''
The andbug.proto module abstracts the JDWP wire protocol into a more 
manageable request/response API using an input worker thread in the
background and a number of mutexes to control contests for output.
'''
#将JDWP 抽象成一系列“请求/响应”


import socket, tempfile
from threading import Thread, Lock
from Queue import Queue, Empty as EmptyQueue


import andbug.util
from andbug import log
from andbug.jdwp import JdwpBuffer

class EOF(Exception):
    'signals that an EOF[帧结束] has been encountered[遇到、遭遇]'
    def __init__(self, inner = None):
        Exception.__init__(
            self, str(inner) if inner else "EOF"
        )

class HandshakeError(Exception):
    'signals that the JDWP handshake failed'
    def __init__(self):
        Exception.__init__(
            self, 'handshake error, received message did not match'
        )

class ProtocolError(Exception):
    pass

HANDSHAKE_MSG = 'JDWP-Handshake'
HEADER_FORMAT = '4412'
IDSZ_REQ = (
    '\x00\x00\x00\x0B' # Length
    '\x00\x00\x00\x01' # Identifier
    '\x00'             # Flags
    '\x01\x07'         # Command 1:7  IDSizes Command (7)
)

#adb -s [dev] forward localfilesystem: [temp] jdwp [pid]
#adb -s emulator-5554 forward  localfilesystem:/tmp/tmpzeJZR5 jdwp:333 
#与虚拟机建立链接
def forward(pid, dev=None):
    'constructs an adb forward for the context to access the pid via jdwp'
    if dev:
        dev = andbug.util.find_dev(dev)
    pid = andbug.util.find_pid(pid)
    temp = tempfile.mktemp() #创建一个临时文件
    cmd = ('-s', dev) if dev else ()  #'-s', 'emulator-5554'
    cmd += ('forward', 'localfilesystem:' + temp,  'jdwp:%s' % pid) #'-s', 'emulator-5554', 'forward', 'localfilesystem:/tmp/tmpSSCNAl', 'jdwp:843')
    andbug.util.adb(*cmd)
    return temp

#调用时的方式：andbug.proto.connect(andbug.proto.forward(pid, dev))
#self.sess = andbug.vm.connect(self.pid, self.dev)
# addr 参数是一个临时文件的路径
def connect(addr, portno = None, trace=False):
    'connects to an AF_UNIX or AF_INET JDWP transport'
    if addr and portno:
        conn = socket.create_connection((addr, portno))
    elif isinstance(addr, int):
        conn = socket.create_connection(('127.0.0.1', addr))
    else:
        conn = socket.socket(socket.AF_UNIX)
        conn.connect(addr)

	#负责读出数据的函数
    def read(amt):
        'read wrapper internal to andbug.proto.connect'
        req = amt
        buf = ''
        while req:
            pkt = conn.recv(req)
            if not pkt: raise EOF()
            buf += pkt
            req -= len(pkt)
        if trace:
            print ":: RECV:", repr(buf)
        return buf 
    
	#负责写入数据的函数
    def write(data):
        'write wrapper internal to andbug.proto.connect'
        try:
            if trace:
                print ":: XMIT:", repr(data)
            conn.sendall(data)
        except Exception as exc:
            raise EOF(exc)
        
    p = Connection(read, write)  #定义一个Connection对象
    p.start()
    return p

class Connection(Thread):
    '''
    The JDWP Connection is a thread which abstracts the asynchronous[异步] JDWP protocol
    into a more synchronous one.  The thread will listen for packets using the
    supplied[提供] read function, and transmit[传送] them using the write function.  

    Requests are sent by the processor using the calling thread, with a mutex 
    used to protect the write function from concurrent[并发的] access.  The requesting
    thread is then blocked waiting on a response from the processor thread.

    The Connectionor will repeatedly use the read function to receive packets, which
    will be dispatched based on whether they are responses to a previous request,
    or events.  Responses to requests will cause the requesting thread to be
    unblocked, thus simulating a synchronous request.
    '''

    def __init__(self, read, write):
        Thread.__init__(self)
        self.xmitbuf = JdwpBuffer()  #具体实现在jdwp文件中，用C语言实现，这块需要了解C语言嵌入python语言的知识
        self.recvbuf = JdwpBuffer()
        self._read = read
        self.write = write
        self.initialized = False
        self.next_id = 3  #下一个请求id，『可能每次请求都是有序号的』
        self.bindqueue = Queue()  #定义一个先进先出的队列
        self.qmap = {}   #初始化一个空的字典
        self.rmap = {}   #初始化一个空的字典
        self.xmitlock = Lock()  #是一个互斥锁

    #读数据的函数，sz准备读取数据的长度，
    def read(self, sz):
        'read size bytes'
        if sz == 0: return ''
        pkt = self._read(sz)  #返回值是读到的数据
        if not len(pkt): raise EOF()   #如果读到的数据的长度为0，抛出EOF异常
        return pkt

    ###################################################### INITIALIZATION STEPS
    
    #写入id序列信息
    def writeIdSzReq(self):
        'write an id size request'
        return self.write(IDSZ_REQ)

	#读取各id的长度信息
    def readIdSzRes(self):
        'read an id size response'
        head = self.readHeader()  #读到的header的值是：list: [20L, 1L, 128L, 0L] ［Length, Id，Flags, Error Code］
        if head[0] != 20: #id size命令的返回数据包的长度为20字节，其中包括11字节的包头长度。
            raise ProtocolError('expected size of an idsize response') #抛出协议错误异常
        if head[2] != 0x80:  #返回包包头中的Flags字段的值是固定的均为0x80即128
            raise ProtocolError(
                'expected first server message to be a response' #抛出协议错误异常
            )
        if head[1] != 1: #由于发送id size请求包的id编号是1，所以合法的返回包的编号也应用是1
            raise ProtocolError('expected first server message to be 1')  #抛出协议错误异常

        sizes = self.recvbuf.unpack( 'iiiii', self.read(20) )
        self.sizes = sizes #读取到的sizes的值是 list: [4L, 4L, 8L, 8L, 8L] 记录下各类型对象所占空间的长度
        self.recvbuf.config(*sizes) 
        self.xmitbuf.config(*sizes)
        return None

	#接收握手数据
    def readHandshake(self):
        'read the jdwp handshake'
        data = self.read(len(HANDSHAKE_MSG))
        if data != HANDSHAKE_MSG:
            raise HandshakeError()  #抛出握手失败异常
    #发送握手数据    
    def writeHandshake(self):
        'write the jdwp handshake'
        return self.write(HANDSHAKE_MSG)

    ############################################### READING / PROCESSING PACKETS
    
    #读取头，在readIdSzRes(self)函数中被调用
    def readHeader(self):
        'reads a header and returns [size, id, flags, event]'
        head = self.read(11)  
        data = self.recvbuf.unpack(HEADER_FORMAT, head)  #unpack函数在jdwp文件中实现
        data[0] -= 11
        return data
    #启动新的线程，来处理从虚拟机中返回的信息。process函数被放在一个死循环中不断调用
    def process(self):
        'invoked repeatedly by the processing thread'

        size, ident, flags, code = self.readHeader() #TODO: HANDLE CLOSE  #读取数据头，包含一下元素size、ident、flags、code
        log.debug("study", "In Connection(Thread).process size=" + str(size) + "\t ident="+ str(ident) + "\t flags=" +str(flags) + "\t code=" + str(code))
        data = self.read(size) #TODO: HANDLE CLOSE  #根据Header中的长度信息，读取具体数据。
        try: # We process binds[绑定] after receiving messages to prevent a race
            while True:
                self.processBind(*self.bindqueue.get(False)) #bindqueue.get(False)参数为False，队列将引发Empty异常
        except EmptyQueue:
            log.debug("study", "Except for Empty Queue")
            pass

        #TODO: update binds with all from bindqueue
        #对于来自虚拟机的事件消息，self.processBind(*self.bindqueue.get(False))不起作用，直接触发EmptyQueue异常，后续调用processRequest函数
        if flags == 0x80:  
            self.processResponse(ident, code, data)  #答复数据包的flag是0x80
        else:
            self.processRequest(ident, code, data)  #请求数据包的flag是0x00
    #函数调用的参数为：qr="r" ident=16484=0x4064 chan 是一个在Session类中定义的一个队列。qr="q" ident=3 其中ident是请求的编号id，调试器发往虚拟机的id从3开始
    def processBind(self, qr, ident, chan):
        'internal[内部的] to i/o thread; performs a query or request bind'
		#根据qr值的不同，以ident为关键字，以chan为值，放入不同的字典中
        log.debug("study", "In Connection(Thread).processBind qr=" + str(qr) + "\t ident=" + str(ident) + "\t chan=" + str(chan))
        log.debug("study", "++bindqueue.get  FOR q ++")
        if qr == 'q':
            self.qmap[ident] = chan  
        elif qr == 'r':
            self.rmap[ident] = chan
           

	#处理请求
    ##请求数据包的flag是0x00
    def processRequest(self, ident, code, data):
        'internal to the i/o thread w/ recv ctrl; processes incoming request'
        log.debug("study", "In Connection.processRequest ident=" + str(ident) + "\t code=" + str(code) + "\t data=")
        chan = self.rmap.get(code)  #所有中断都由该chan队列处理，每次只是从rmap读出内容，而没有将rmap对应的chan清除
        if not chan: return #TODO
        buf = JdwpBuffer()
        buf.config(*self.sizes)
        buf.prepareUnpack(data)
        return chan.put((ident, buf)) #将解析后的数据压入队列中
     
	#处理相应，chan变量是什么类型的需要关注，其与类的队列成员变量self.bindqueue有关
    #答复数据包的flag是0x80   
    def processResponse(self, ident, code, data):
        'internal to the i/o thread w/ recv ctrl; processes incoming response'
        log.debug("study", "In Connection.processResponse ident=" + str(ident) + "\t code=" + str(code) + "\t data=")
        chan = self.qmap.pop(ident, None) #从字典中读取，并删除该数据
        if not chan: return
        buf = JdwpBuffer()
        buf.config(*self.sizes)
        buf.prepareUnpack(data)
        return chan.put((code, buf))

	#调用的实际情况为：conn.hook(0x4064, self.evtq)，其中self.evtq是一个队列
    def hook(self, code, chan):
        '''
        when code requests are received, they will be put in chan for
        processing
        '''

		#使用锁
        with self.xmitlock:
            self.bindqueue.put(('r', code, chan)) #加入一个先进先出的队列
            log.debug("study", "++ for hook function bindqueue.put  FOR r ++ code=" + str(code))
        
    ####################################################### TRANSMITTING PACKETS
    
	#申请一个请求id
    def acquireIdent(self):
        'used internally by the processor; must have xmit[传输] control'
        ident = self.next_id
        self.next_id += 2
        return ident

	#发送[写入]指定的数据
    def writeContent(self, ident, flags, code, body):
        'used internally by the processor; must have xmit control'

        size = len(body) + 11
        self.xmitbuf.preparePack(11)
        data = self.xmitbuf.pack(
            HEADER_FORMAT, size, ident, flags, code
        )
        self.write(data)
        return self.write(body)

	#构造请求
    def request(self, code, data='', timeout=None):
        'send a request, then waits for a response; returns response'
        queue = Queue()
        log.debug("study", "In Connection.request code=" + str(code) + "\t data=" + str(data))
        with self.xmitlock:
            ident = self.acquireIdent()
            self.bindqueue.put(('q', ident, queue)) #每发送一个请求向bindqueue中压入一个数据
            log.debug("study", "++bindqueue.put  FOR q ++")
            self.writeContent(ident, 0x0, code, data)
        
        try:
            log.debug("study", "wait_code:" + str(code))
            return queue.get(1, timeout)  #向虚拟机发出指令后一直处于等待状态，知道queue队列中出现返回信息，接下来处理
        except EmptyQueue:
            return None, None

    def buffer(self):
        'returns a JdwpBuffer configured for this connection'
        buf = JdwpBuffer()
        buf.config(*self.sizes)
        return buf
        
    ################################################################# THREAD API
    
    def start(self):
        'performs handshaking and solicits[恳求] configuration information'
        self.daemon = True  #守护线程

        if not self.initialized: #如果为false初始化尚未完成，完成下面初始化工作
            self.writeHandshake()
            self.readHandshake()
            self.writeIdSzReq()
            self.readIdSzRes()
            self.initialized = True #确认完成初始话
            Thread.start(self)
        return None

    def run(self):
        'runs forever; overrides the default Thread.run()'
        try:
            while True:
                self.process()
        except EOF:
            return
    
