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


import threading, re
from andbug.data import defer
from threading import Lock
from Queue import Queue
import json


import andbug #andbug.data, andbug.proto, andbug.screed
from andbug import log
import traceback

g_jdwp_request_timeout =2

## Implementation Questions:
## -- unpackFrom methods are used to unpack references to an element from
##    a JDWP buffer.  This does not mean unpacking the actual definition of
##    the element, which tends to be one-shot.
##
## References:
## -- All codes that are sent to Dalvik VM where extracted from
##    dalvik/vm/jdwp/JdwpHandler.cpp and converted to HEX values
##    (e.g. Resume Thread: {11, 3, ....} => 0b03)
## -- JDWP Protocol:
##    dalvik implements a subset of these, verify with JdwpHandler.cpp:
##    http://docs.oracle.com/javase/6/docs/platform/jpda/jdwp/jdwp-protocol.html
##    

class RequestError(Exception):
    'raised when a request for more information from the process fails'
    def __init__(self, code):
        Exception.__init__(self, 'request failed, code %s' % code)
        self.code = code

class Element(object):
    def __repr__(self):  #以打印方式，输出字符串
        return '<%s>' % self

    def __str__(self):  #输出字符串
        return '%s:%s' % (type(self).__name__, id(self))

class SessionElement(Element):
    def __init__(self, sess):
        self.sess = sess

    @property
    def conn(self):
        return self.sess.conn
    
    
#主要是指类的成员变量
class Field(SessionElement):
    def __init__(self, session, fid):
        SessionElement.__init__(self, session)
        self.fid = fid
    def __str__(self):
        field_str = self.get_property() + " " + str(self.jni) + " "+ str(self.name)
        return field_str
    
    @classmethod 
    def unpackFrom(impl, sess, buf):
        return sess.pool(impl, sess, buf.unpackFieldId())
    
    @property
    def public(self):
        return self.flags & 0x0001
    
    @property
    def private(self):
        return self.flags & 0x0002
    
    @property
    def protected(self):
        return self.flags & 0x0004
    
    @property
    def static(self):
        return self.flags & 0x0008
    
    @property
    def final(self):
        return self.flags & 0x0010

    @property
    def volatile(self):
        return self.flags & 0x0040
    
    @property
    def transient(self):
        return self.flags & 0x0080
    
    
    def get_property(self):
        '''
        判断field的属性是什么样的，如public static        
        '''
        property_value= ""
        if self.public:
            property_value="public "
        if self.private:
            property_value = property_value + "private "
        if self.protected:
            property_value = property_value + "protected "
        if self.static:
            property_value = property_value + "static "            
        if self.final:
            property_value = property_value + "final "   
        if self.volatile:
            property_value = property_value + "volatile "             
        if self.transient:
            property_value = property_value + "transient "     
        
        return property_value
            
            
            
            
            
            
            
            
            
            
            
            
            
    
class Value(SessionElement):
    @property
    def isPrimitive(self):
        return self.TAG in PRIMITIVE_TAGS

    @property
    def isObject(self):
        return self.TAG in OBJECT_TAGS

class Frame(SessionElement):
    def __init__(self, sess, fid):
        SessionElement.__init__(self, sess)
        self.fid = fid
        self.loc = None
        self.tid = None

    def __str__(self):
        return 'frame %s, at %s' % (self.fid, self.loc)   

    @classmethod 
    def unpackFrom(impl, sess, buf):
        return sess.pool(impl, sess, buf.unpackFrameId()) #创建一个Frame类型的对象
    
    def packTo(self, buf):
        buf.packFrameId(self.fid)

    @property
    def native(self):
        return self.loc.native

    @property
    def values(self):
        '''
        1、命令  0x0a 0x01
        2、注释：堆栈命令集
        3、[StackFrame Command Set (16)][GetValues Command (1)]
        '''
        vals = {}
        if self.native: return vals  #如果是系统函数返回空
        
        sess = self.sess
        conn = self.conn
        buf = conn.buffer()
        buf.packObjectId(self.tid)  #thread id
        buf.packFrameId(self.fid) #frame id
        slots = self.loc.slots  
        log.debug("study", "In frame thread_id=" + str(self.tid))
        log.debug("study", "In frame frame_id=" + str(self.fid))
        log.debug("study", "In frame len(slots)=" + str(len(slots)))
        buf.packInt(len(slots))  #The number of values to get.   要获取局部变量的个数

        for slot in slots:
            buf.packInt(slot.index)  #The local variable's index in the frame.  局部变量的索引值
            buf.packU8(slot.tag) #TODO: GENERICS  #A tag identifying the type of the variable  标志变量类型的标签
            log.debug("study", "In frame slot.index=" + str(slot.index))
            log.debug("study", "In frame slot.tag=" + str(slot.tag))
            
        log.debug("study", "call jdwp 0x10 01")
        code, buf = conn.request(0x1001, buf.data(), g_jdwp_request_timeout)
        if code != 0:
            raise RequestError(code)
        ct = buf.unpackInt()

        for x in range(0, ct):
            s = slots[x]
            vals[s.name] = unpack_value(sess, buf) #The number of values retrieved, always equal to slots, the number of values to get. 

            log.debug("study", "In frame vals[%s]= %s"%(s.name, vals[s.name]))
            log.debug("study", "In frame date for String= %s"%(buf))
        return vals

    def value(self, name):
        if self.native: return None

        sess = self.sess
        conn = self.conn
        buf = conn.buffer()
        buf.packObjectId(self.tid)
        buf.packFrameId(self.fid)
        slots = self.loc.slots
        buf.packInt(1)

        loc = None
        for i in range(0, len(slots)):
            if slots[i].name == name:
                loc = i
                break
            else:
                continue

        if loc is None:
            return None
        slot = slots[loc]
        buf.packInt(slot.index)
        buf.packU8(slot.tag) #TODO: GENERICS

        code, buf = conn.request(0x1001, buf.data())
        if code != 0:
            raise RequestError(code)
        if buf.unpackInt() != 1:
            return None

        return unpack_value(sess, buf)

    def setValue(self, name, value):
        if self.native: return False

        sess = self.sess
        conn = self.conn
        buf = conn.buffer()
        buf.packObjectId(self.tid)
        buf.packFrameId(self.fid)
        slots = self.loc.slots
        buf.packInt(1)

        loc = None
        for i in range(0, len(slots)):
            if slots[i].name == name:
                loc = i
                break
            else:
                continue

        if loc is None:
            return False
        slot = slots[loc]
        buf.packInt(slot.index)
        pack_value(sess, buf, value, slot.jni) #TODO: GENERICS

        code, buf = conn.request(0x1002, buf.data())
        if code != 0:
            raise RequestError(code)

        return True

class Thread(SessionElement):
    #TODO: promote to Value
    def __init__(self, sess, tid):
        SessionElement.__init__(self, sess)
        self.tid = tid
    
    def __str__(self):
        tStatus, sStatus = self.status
        return 'thread %s\t(%s %s)' % (self.name or hex(self.tid), Thread.threadStatusStr(tStatus), Thread.suspendStatusStr(sStatus))

    def suspend(self):  
        ''' 
        1、似乎命令应该是0x0b 0x01 暂停线程的命令  [ThreadReference Command Set (11)][Suspend Command (2)]
        2、用于暂停单个线程。
        
        '''
        conn = self.conn
        buf = conn.buffer()
        buf.packObjectId(self.tid)
        log.debug("study", "call jdwp 0x0B 01")
        code, buf = conn.request(0x0B01, buf.data(), g_jdwp_request_timeout)
        if code != 0:
            raise RequestError(code)

    def resume(self):
        ''' 
            1、命令是0x0b 0x03 重新启动线程  [ThreadReference Command Set (11)][Resume Command (3)]
            2、启动之前的线程
        '''
        conn = self.conn
        buf = conn.buffer()
        buf.packObjectId(self.tid)
        log.debug("study", "call jdwp 0x0B 03")
        code, buf = conn.request(0x0B03, buf.data(), g_jdwp_request_timeout)
        if code != 0:
            raise RequestError(code)

    def packTo(self, buf):
        buf.packObjectId(self.tid)

    def hook(self, func = None, queue = None):
        conn = self.conn
        buf = conn.buffer()
        # 40:EK_METHOD_ENTRY, 1: SP_THREAD, 1 condition of type ClassRef (3), ThreadId
        log.debug("study", "call jdwp 0x0f 01")
        buf.pack('11i1t', 40, 1, 1, 3, self.tid) 
        code, buf = conn.request(0x0f01, buf.data())
        if code != 0:
            raise RequestError(code)
        eid = buf.unpackInt()
        return self.sess.hook(eid, func, queue, self)

    @classmethod
    def unpackFrom(impl, sess, buf):
        tid = buf.unpackObjectId()  #获取当前线程的ID值
        return sess.pool(impl, sess, tid)  #创造一个Thred类，sess和tid是传递给构造函数的变量

    @property
    def frames(self):
        '''命令 0x0b 0x06 功能返回当前挂起线程的堆栈信息，  [ThreadReference Command Set (11)][Frames Command(6)]
        '''
        tid = self.tid
        sess = self.sess
        conn = self.conn  #conn是Connection类型的变量
        buf = conn.buffer()
        buf.pack('oii', self.tid, 0, -1) #三个参数，tid 线程id；0表示从堆栈最开始位置获取，；-1表示获取所有的堆栈信息
        log.debug("study", "call jdwp 0x0B 06")
        code, buf = conn.request(0x0B06, buf.data(), g_jdwp_request_timeout)
        if code != 0:
            raise RequestError(code)
        ct = buf.unpackInt() #堆栈信息的个数
        #这个jdwp命令返回的数据是：ct：堆栈的个数，frameID：每个堆栈的id；location：位置信息
        
        def load_frame(): #用来解析返回的堆栈数据
            f = Frame.unpackFrom(sess, buf) #f为返回的Frame堆栈类型的对象
            f.loc = Location.unpackFrom(sess, buf) #Location类型的对象
            f.tid = tid #传递当前线程的id
            return f

        return andbug.data.view(load_frame() for i in range(0,ct))

    @property
    def frameCount(self): 
        '''命令: 0x0b 0x07
                                 功能 : 获取挂起线程的堆栈帧的个数
            [ThreadReference Command Set (11)][FrameCount Command (7)#]
        '''  
        conn = self.conn
        buf = conn.buffer()
        buf.packObjectId(self.tid)
        log.debug("study", "call jdwp 0x0B 07")
        code, buf = conn.request(0x0B07, buf.data(), g_jdwp_request_timeout)
        if code != 0:
            raise RequestError(code)
        return buf.unpackInt()

    @property
    def name(self): 
        '''命令: 0x0b 0x01
                                 功能 : 获取线程名称
            [ThreadReference Command Set (11)][FrameCount Command (1)#]
        '''   
        conn = self.conn
        buf = conn.buffer()
        buf.packObjectId(self.tid)
        log.debug("study", "call jdwp 0x0B 01")
        code, buf = conn.request(0x0B01, buf.data(), g_jdwp_request_timeout)
        if code != 0:
            raise RequestError(code)
        return buf.unpackStr()

    @property
    def status(self):
        conn = self.conn
        buf = conn.buffer()
        buf.packObjectId(self.tid)
        code, buf = conn.request(0x0b04, buf.data())
        if code != 0:
            raise RequestError(code)

        threadStatus = buf.unpackInt()
        suspendStatus = buf.unpackInt()

        return threadStatus, suspendStatus

    @staticmethod
    def threadStatusStr(tStatus):
        szTS = ('zombie', 'running', 'sleeping', 'monitor', 'waiting', 'initializing', 'starting', 'native', 'vmwait')
        tStatus = int(tStatus)
        if tStatus < 0 or tStatus >= len(szTS):
            return "UNKNOWN"
        return szTS[tStatus]

    @staticmethod
    def suspendStatusStr(sStatus):
        szSS = ('running', 'suspended')
        sStatus = int(sStatus)
        if sStatus < 0 or sStatus >= len(szSS):
            return "UNKNOWN"
        return szSS[sStatus]

class Location(SessionElement):
    '''
    类功能：描述代码中的一个位置
    '''
    def __init__(self, sess, tid, mid, loc):
        SessionElement.__init__(self, sess)
        self.tid = tid  #class type id
        self.mid = mid  #method id
        self.loc = loc  #long 类型的整数
        self.line = None
        log.debug("study", "in Loction class: tid=" + str(tid) + "\t mid=" + str(mid) + "\t loc=" + str(loc))

    def __str__(self):
        if self.loc >= 0:
            return '%s:%i' % (self.method, self.loc)
        else:
            return str(self.method)

    def packTo(self, buf):
        c = self.klass
        buf.ipack('1tm8', c.tag, self.tid, self.mid, self.loc)
        log.debug("study", "in Location.packTo: tag=" + str(c.tag) + "\t tid=" + str(c.tid) + "\t mid=" + str(self.mid) + "\t loc=" + str(self.loc))

    @classmethod #类方法
    def unpackFrom(impl, sess, buf):
        tag, tid, mid, loc = buf.unpack('1tm8')
        log.debug("study", "In Location.unpackFrom: tag=" + str(tag) + "\t tid=" + str(tid) + "\t mid=" + str(mid) + "\t loc=" + str(loc))
        return sess.pool(impl, sess, tid, mid, loc)  #设置一个Location类型

    def hookOut(self, func=None, queue=None):
        '''
        功能：函数调用结束时，将程序hook终端
        '''
        conn = self.conn
        buf = conn.buffer()
        # 40:EK_METHOD_ENTRY, 1: EVENT_THREAD, 1 condition of type Location (7) Case LocationOnly - if modKind is 7:
        buf.pack('11i1', 41, 1, 1, 7)  #只实现了METHOD_ENTRY方法入口事件的处理，其他事件没有处理

        self.packTo(buf) #在这里将loc传入jdwp的参数，
        log.debug("study", "call jdwp 0x0F 01")
        code, buf = conn.request(0x0F01, buf.data(), g_jdwp_request_timeout)
        if code != 0:
            raise RequestError(code)
        eid = buf.unpackInt() #返回的是一个ID of created request，用来区别与这个断点
        log.debug("study", "eid=" + str(eid))   
        return self.sess.hook(eid, func, queue, self) #queue参数为空  sess的类型是Session

    def hook(self, func = None, queue = None):
        '''
            命令：0x0f 0x01
            功能：设置一个事件请求，调用指定函数时，中断函数
            [EventRequest Command Set (15)] [Set Command (1)]
            注：所设置的具体事件由 buf.pack('11i1', 40, 1, 1, 7) 确定
        '''
        conn = self.conn
        buf = conn.buffer()
        # 40:EK_METHOD_ENTRY, 1: EVENT_THREAD, 1 condition of type Location (7) Case LocationOnly - if modKind is 7:
        # 2: BREAKPOINT
        # 40:METHOD_ENTRY
        # 41:METHOD_EXIT
        if self == self.method.firstLoc:
            eventKind = 40
        elif self == self.method.lastLoc:
            eventKind = 41
        else:
            eventKind = 2
        # 1: SP_THREAD, 1 condition of type Location (7)
        buf.pack('11i1', eventKind, 1, 1, 7)  #只实现了METHOD_ENTRY方法入口事件的处理，其他事件没有处理

        self.packTo(buf) #在这里将loc传入jdwp的参数，
        log.debug("study", "call jdwp 0x0F 01")
        code, buf = conn.request(0x0F01, buf.data(), g_jdwp_request_timeout)
        if code != 0:
            raise RequestError(code)
        eid = buf.unpackInt() #返回的是一个ID of created request，用来区别与这个断点
        log.debug("study", "eid=" + str(eid))   
        return self.sess.hook(eid, func, queue, self) #queue参数为空  sess的类型是Session

    @property
    def native(self):
        return self.loc == -1

    @property
    def method(self):
        return self.sess.pool(Method, self.sess, self.tid, self.mid)

    @property
    def klass(self):
        return self.sess.pool(Class, self.sess, self.tid)  #从sess中找指定tid的class对象，这里应该能够找到（之前已经创建了），返回该class对象

    @property
    def slots(self):
        log.debug("study", "In Location slots")
        l = self.loc
        def filter_slots():
            for slot in self.method.slots:                
                f = slot.firstLoc
                log.debug("study", "In Location.slots l=" + str(l) + "\t f=" + str(f))
                if f > l: continue
                if l - f > slot.locLength: continue
                yield slot
        return tuple() if self.native else tuple(filter_slots())#如果是系统函数，返回没有内容的空元组
        '''
            In Location.slots l=9     f=93
            In Location.slots l=9     f=93
            In Location.slots l=9     f=93
            In Location.slots l=9     f=173
            In Location.slots l=9     f=150
            In Location.slots l=9     f=156
            In Location.slots l=9     f=144
            In Location.slots l=9     f=93
            In Location.slots l=9     f=2
            In Location.slots l=9     f=93
            In Location.slots l=9     f=1
            In Location.slots l=9     f=93
            In Location.slots l=9     f=0
        '''
class Slot(SessionElement):
    '''
    类的功能：描述一个变量的信息，主要用来描述成员函数中的成员变量和函数参数
    '''
    def __init__(self, sess, tid, mid, index):
        SessionElement.__init__(self, sess)
        self.tid = tid
        self.mid = mid
        self.index = index
        self.name = None

    def __str__(self):
        if self.name:
            return 'slot %s at index %i' % (self.name, self.index)
        else:
            return 'slot at index %i' % (self.index)

    def load_slot(self):
        log.debug("study", "############In slot.load ")
        self.sess.pool(Class, self.sess, self.tid).load_slots()

    firstLoc = defer(load_slot, 'firstLoc')
    locLength = defer(load_slot, 'locLength')
    name = defer(load_slot, 'name')
    jni = defer(load_slot, 'jni')
    gen = defer(load_slot, 'gen')

    @property
    def tag(self):
        return ord(self.jni[0])

class Method(SessionElement):
    def __init__(self, sess, tid, mid):
        SessionElement.__init__(self, sess)
        self.tid = tid   #refType id 的值
        self.mid = mid   #method id 的值

    @property
    def klass(self):
        return self.sess.pool(Class, self.sess, self.tid) #这里是TypeId

    def __str__(self):
        return '%s.%s%s' % (
            self.klass, self.name, self.jni 
    )       
     
    def __repr__(self):
        return '<method %s>' % self

    def load_line_table(self):
        '''
                                命令：0x06 0x01
                                功能：返回函数的行号信息
            [Method Command Set (6)][LineTable Command (1)]
        '''
        
        if self.abstract!=0:
            #说明当前方法是一个抽象方法
            log.debug("study", "the function [" + self.name + "]is abstract function")
            log.debug("study", "flag:" + str(self.flags))
            log.debug("study", "abstract:" + str(self.abstract))
            self.firstLoc = None
            self.lastLoc = None
            self.lineTable = None
            return 
        
        sess = self.sess
        conn = sess.conn
        pool = sess.pool
        tid = self.tid
        mid = self.mid
        data = conn.buffer().pack('om', tid, mid) #输入参数是type id和method id
        log.debug("study", "call jdwp 0x06 01")
        code, buf = conn.request(0x0601, data, g_jdwp_request_timeout)
        log.debug("study", "finish " + str(buf)+ " code:" + str(code))
        if code != 0:  
            raise RequestError(code)
        
        
        
        f, l, ct = buf.unpack('88i')
        log.debug("study", "firstLoc=" + str(f) + "\t lastLoc=" + str(l) + "\t lineTable=" + str(ct))
        if (f == -1) or (l == -1):             
            self.firstLoc = None
            self.lastLoc = None
            self.lineTable = andbug.data.view([])
            #TODO: How do we handle native methods?
      
        self.firstLoc = pool(Location, sess, tid, mid, f) #声明一个Locaton类来保存获取的locaiton信息       
        self.lastLoc = pool(Location, sess, tid, mid, l)
        

        ll = {}
        #self.lineLocs = ll    #这个变量是否应该是lineTable，在正常路径中linetable没有赋值
        self.lineTable = ll
        def line_loc(): #根据获取的函数的代码行数信息，逐行取出代码信息
            loc, line  = buf.unpack('8i')
            log.debug("study", "loc="+ str(loc) + "\t line=" + str(line))           
            loc = pool(Location, sess, tid, mid, loc)           
            loc.line = line            
            ll[line] = loc
         

        for i in range(0,ct):            
            line_loc()
      
    
    firstLoc = defer(load_line_table, 'firstLoc')   #methods类中的变量，所以对于每个方法都会有这些信息
    lastLoc = defer(load_line_table, 'lastLoc')
    lineTable = defer(load_line_table, 'lineTable')

    

    def load_method(self):
        self.klass.load_methods()

    name = defer(load_method, 'name')
    jni = defer(load_method, 'jni')
    gen = defer(load_method, 'gen')
    flags = defer(load_method, 'flags' )

    def load_slot_table(self):
        '''
            1 命令：0x06  0x05
            2 功能：获取一个方法中的参数和变量的信息
            3 解释： [Method Command Set (6)][VariableTableWithGeneric Command (5)]
        '''
        sess = self.sess
        conn = self.conn
        pool = sess.pool
        tid = self.tid
        mid = self.mid
        data = conn.buffer().pack('om', tid, mid)
        log.debug("study", "In Method.load_slot_table classTypeId=" + str(tid) + "\t mid=" + str(mid))
        log.debug("study", "call jdwp 0x06 05")
        code, buf = conn.request(0x0605, data, g_jdwp_request_timeout)
        if code != 0: raise RequestError(code)
    
        act, sct = buf.unpack('ii')  #获取参数的个数，获取自变量的个数
        self.arg_cnt = act
        self.slot_cnt = sct
        log.debug("study", "In Method.load_slot_table argCount=" + str(act) + "\t sct=" + str(sct))
        #TODO: Do we care about the argCnt ?
         
        def load_slot():
            codeIndex, name, jni, gen, codeLen, index  = buf.unpack('l$$$ii')
            slot = pool(Slot, sess, tid, mid, index)
            slot.firstLoc = codeIndex
            slot.locLength = codeLen
            slot.name = name
            slot.jni = jni
            slot.gen = gen
            log.debug("study", "In Method.load_slot_table.load_slot firstLoc=" + str(slot.firstLoc) + "\t locLength=" + str(slot.locLength) + "\t name=" + str(slot.name) + "\t jni=" + str(slot.jni) + "\t gen=" + str(slot.gen))

            return slot

        self.slots = andbug.data.view(load_slot() for i in range(0,sct))

    slots = defer(load_slot_table, 'slots')
    
    

    def load_bytecodes (self):
        '''
        函数功能：获得一个函数的字节码
        注：dilvik 暂时不支持通过0x0603指令获得函数字节码的功能
        '''
        sess = self.sess
        conn = self.conn
        pool = sess.pool
        tid = self.tid
        mid = self.mid
        bytecode = ''
        data = conn.buffer().pack('om', tid, mid)
        log.debug("study", "call jdwp 0x06 05")
        code, buf = conn.request(0x0603, data, g_jdwp_request_timeout)
        if code !=0: raise RequestError(code)
        
        bytecodeLen = buf.unpack('i')
        
        for i in range(0,bytecodeLen):
            bytecode += buf.unpackU8()
            
        log.debug("study", "bytecode=" + bytecode)
        

    @property
    def public(self):
        return self.flags & 0x0001        

    @property
    def private(self):
        return self.flags & 0x0002  
    
    @property
    def protected(self):
        return self.flags & 0x0004   
    
    @property 
    def static(self):
        return self.flags & 0x0008
    
    @property 
    def final(self):
        return self.flags & 0x0010    
    
    
    @property 
    def synchronized(self):
        return self.flags & 0x0020    
    
    
    @property 
    def bridge(self):
        return self.flags & 0x0040    
    
    @property 
    def varargs(self):
        return self.flags & 0x0080     
    
    @property 
    def native(self):
        return self.flags & 0x0100     
    
    @property 
    def abstract(self):
        return self.flags & 0x0400    
    
    @property 
    def strict(self):
        return self.flags & 0x0800     
    
    @property 
    def synthetic(self):
        return self.flags & 0x1000     
    
    def get_property(self):
        '''
        判断field的属性是什么样的，如public static        
        '''
        
        property_value= ""
        if self.public:
            property_value="public "
        if self.private:
            property_value = property_value + "private "
        if self.protected:
            property_value = property_value + "protected "
        if self.static:
            property_value = property_value + "static "            
        if self.final:
            property_value = property_value + "final "   
        if self.synchronized:
            property_value = property_value + "synchronized "             
        if self.bridge:
            property_value = property_value + "bridge "
        if self.varargs:
            property_value = property_value + "varargs "
        if self.native:
            property_value = property_value + "native " 
        if self.abstract:
            property_value = property_value + "abstract " 
        if self.strict:
            property_value = property_value + "strict "             
        if self.synthetic:
            property_value = property_value + "synthetic "     
        
        return property_value
    

class RefType(SessionElement):
    def __init__(self, sess, tag, tid):
        SessionElement.__init__(self, sess)
        self.tag = tag
        self.tid = tid
        log.debug("study", "in RefType class: tag=" + str(tag) + "\t tid=" + str(tid))
    
    def __repr__(self):
        return '<type %s %s#%x>' % (self.jni, chr(self.tag), self.tid)

    def __str__(self):
        return repr(self)

    @classmethod 
    def unpackFrom(impl, sess, buf):
        return sess.pool(impl, sess, buf.unpackU8(), buf.unpackTypeId())

    def packTo(self, buf):
        buf.packObjectId(self.tid)

    def load_signature(self):
        ''''
        1 命令： 0x02 0x0d
        2 功能：返回引用类型的JNI signature和generic signature
        3 解释：[ReferenceType Command Set (2)][SignatureWithGeneric Command (13)]
        '''
        conn = self.conn
        buf = conn.buffer()
        self.packTo(buf)
        log.debug("study", "call jdwp 0x02 0d")
        code, buf = conn.request(0x020d, buf.data(), g_jdwp_request_timeout)
        if code != 0:
            raise RequestError(code)
        self.jni = buf.unpackStr()
        self.gen = buf.unpackStr()

    gen = defer(load_signature, 'gen')
    jni = defer(load_signature, 'jni')

    def load_fields(self):
        ''''
        1 命令： 0x02 0x0e
        2 功能：返回信息，包括 引用类型中每一个字段的通用签名
        3 解释：[ReferenceType Command Set (2)][FieldsWithGeneric Command (14)]
        '''      
        sess = self.sess
        conn = self.conn
        buf = conn.buffer()
        buf.pack("t", self.tid)
        log.debug("study", "load_fields tid=" + str(self.tid))
        log.debug("study", "call jdwp 0x02 0E")
        code, buf = conn.request(0x020E, buf.data(), g_jdwp_request_timeout)
        if code != 0:
            raise RequestError(code)

        ct = buf.unpackU32()

        def load_field():
            field = Field.unpackFrom(sess, buf) #先获取field的值
            name, jni, gen, flags = buf.unpack('$$$i')
            #log.debug("study", "field_id="+ str(field) +"\t name=" + str(name) + "\t jni=" + str(jni) + "\t gen=" + str(gen) + "\t flags="+ str(flags))
            field.name = name
            field.jni = jni
            field.gen = gen
            field.flags = flags
            return field
        
        self.fieldList = andbug.data.view(
            load_field() for i in range(ct)
        )        

    fieldList = defer(load_fields, 'fieldList')

    @property
    def statics(self):
        ''''
        1 命令： 0x02 0x06
        2 功能：返回一个引用类型中的一个或多个静态变量的值
        3 解释：[ReferenceType Command Set (2)][GetValues Command (6)]
        4 输入参数：指定类的type id的值
                  这个类中的静态变量的个数
                  各静态变量的field id值     
        '''
        sess = self.sess
        conn = self.conn
        buf = conn.buffer()
        buf.packTypeId(self.tid)        
        fields = list(f for f in self.fieldList if f.static)  #这里在在发起0x0206命令时，会访问
        buf.packInt(len(fields))
        log.debug("study", "statics tid(type_id)= " + str(self.tid))
        log.debug("study", "the fields len = " + str(len(fields)))
        
        for field in fields:
            buf.packFieldId(field.fid)
            log.debug("study", "static field id=" + str(field.fid))
            
        log.debug("study", "call jdwp 0x02 06 获取指定类型中的静态变量信息 " )
        code, buf = conn.request(0x0206, buf.data(), g_jdwp_request_timeout) 
        if code != 0:
            raise RequestError(code)
        ct = buf.unpackInt()
        log.debug("study", "in statics ct=" + str(ct))
        vals = {}
        for x in range(ct):
            f = fields[x]           
            vals[f.name] = unpack_value(sess, buf)  #通过调用unpack_value函数，获取的field的值，针对值的不同内容，进行不同的处理
            log.debug("study", "ttt_" + str(vals[f.name]))
            
        log.debug("study", "in statics finish function")
        return vals

    def load_methods(self):
        ''''
        1 命令： 0x02 0x0f
        2 功能：通过一个引用类型返回其包含的方法的通用签名信息
        3 解释：[ReferenceType Command Set (2)][MethodsWithGeneric Command (15)]
        '''
        tid = self.tid
        sess = self.sess
        conn = self.conn
        pool = sess.pool
        buf = conn.buffer()
        buf.pack("t", tid) #传入的值是refType id
        log.debug("study", "call jdwp 0x02 0F "+ str(tid))
        code, buf = conn.request(0x020F, buf.data(), g_jdwp_request_timeout)
        andbug.screed.item("+++call load methods")
        if code != 0:
            raise RequestError(code)

        ct = buf.unpackU32()
                
        def load_method():
            mid, name, jni, gen, flags = buf.unpack('m$$$i') #method_id str str str int
            obj = pool(Method, sess, tid, mid)
            obj.name = name
            obj.jni = jni
            obj.gen = gen
            obj.flags = flags
            infor = "tid="+ str(hex(tid))+ "\t mid=" + str(hex(mid)) + "\t name=" + name + "\t jni=" + jni + "\t gen=" + gen + "\t flags=" + str(hex(flags))
            #infor = "name=" + name + "\t flags=" + str(hex(flags))
            log.debug("study", infor)
        
            return obj
    
        self.methodList = andbug.data.view(
            load_method() for i in range(0, ct)
        )
        self.methodByJni = andbug.data.multidict()
        self.methodByName = andbug.data.multidict()

        for item in self.methodList:
            jni = item.jni
            log.debug("study", str(jni))
            name = item.name
            self.methodByJni[jni] = item
            self.methodByName[name] = item
    
    methodList = defer(load_methods, 'methodList')
    methodByJni = defer(load_methods, 'methodByJni')
    methodByName = defer(load_methods, 'methodByName')

    methodList = defer(load_methods, 'methodList')
    methodByJni = defer(load_methods, 'methodByJni')
    methodByName = defer(load_methods, 'methodByName')

    def methods(self, name=None, jni=None):
        if name and jni:
            log.debug("study", name + "\t" + jni)
            seq = self.methodByName[name]
            log.debug("study", "seq=" + str(seq))
            seq = filter(x in seq, self.methodByJni[jni]) #2.7 版本的python会执行错误
        elif name:
            seq = andbug.data.view(self.methodByName[name])
        elif jni:
            seq = self.methodByJni[jni]
        else:
            seq = self.methodList
        return andbug.data.view(seq)
    
    @property
    def name(self):
        name = self.jni
        if name.startswith('L'): name = name[1:]
        if name.endswith(';'): name = name[:-1]
        name = name.replace('/', '.')
        return name

class Class(RefType): 
    #在obj = self.pool(Class, self, tid) 代码处，会初始化大量的Class类的对象
    def __init__(self, sess, tid): #两个参数分别是：Session类行的变量，与具体类所对应的typeid的值
        RefType.__init__(self, sess, 'L', tid)
        
    def __str__(self):
        return self.name
    
    def __repr__(self):
        return '<class %s>' % self

    def hookEntries(self, func = None, queue = None):
        '''
        1 命令： 0x0f 0x01
        2 功能：设置事件
        3 解释：[EventRequest Command Set (15)][Set Command (1)]
        '''
        conn = self.conn
        buf = conn.buffer()
        # 40:KEK_METHOD_ENTRY, 1: EVENT_THREAD, 1：modifiers（只有一个mod） 4：modKind是4，含义是 condition of type ClassRef (4)
        # 针对4这个modkind值，需要传入一个指定的Reference TypeID 
        buf.pack('11i1t', 40, 1, 1, 4, self.tid)  #tid为type id
        log.debug("study", "call jdwp 0x0F 01")
        code, buf = conn.request(0x0F01, buf.data(), g_jdwp_request_timeout)
        if code != 0:
            raise RequestError(code)
        eid = buf.unpackInt() #返回值是一个requestID ：ID of created request
        log.debug("study", "eid=" + str(eid)) #eid=536870915
        return self.sess.hook(eid, func, queue, self)
        
    #def load_class(self):
    #   self.sess.load_classes()
    #   assert self.tag != None
    #   assert self.flags != None

    #tag = defer(load_class, 'tag')
    #jni = defer(load_class, 'jni')
    #gen = defer(load_class, 'gen')
    #flags = defer(load_class, 'flags')

class Hook(SessionElement):
    def __init__(self, sess, ident, func = None, queue = None, origin = None):
        SessionElement.__init__(self, sess)
        if queue is not None:
            self.queue = queue
        elif func is None:
            self.queue = queue or Queue()
        self.func = func        

        self.ident = ident
        self.origin = origin
        #TODO: unclean
        with self.sess.ectl:
            self.sess.emap[ident] = self   #ident ID of created request 
            log.debug("study", "in Hook __init__ ident=" + str(ident))

    def __str__(self):
        return ('<%s> %s %s' %
            (str(self.ident), str(self.origin), str(type(self.origin))))

    def put(self, data):
        if self.func is not None:
            return self.func(data) #在这里回调事件处理函数，所有参数全部传入回调函数，分别包含Thread类型和Locaion两个类型的对象作为参数
        else:
            return self.queue.put(data)
            
    def get(self, block = False, timeout = None):
        return self.queue.get(block, timeout)

    def clear(self):
        #TODO: unclean
        conn = self.conn
        buf = conn.buffer()
        # 40:EK_METHOD_ENTRY
        buf.pack('1i', 40, int(self.ident))
        # 0x0f02 = {15, 2} EventRequest.Clear
        code, unknown = conn.request(0x0f02, buf.data())
        # fixme: check what a hell is the value stored in unknown
        if code != 0:
            raise RequestError(code)

        with self.sess.ectl:
            del self.sess.emap[self.ident]
            
            
            
class VmCapability(Element):
    '''
    记录当前vm所支持的功能
    '''
    def __init__(self, capabilityBuf, newCapabilityBuf): 
        # reserved16 - reserved32        
        self.vm_cap = {}
        self.vm_cap["canWatchFieldModification"] = newCapabilityBuf.unpackU8()
        self.vm_cap["canWatchFieldAccess"] = newCapabilityBuf.unpackU8()
        self.vm_cap["canGetBytecodes"] = newCapabilityBuf.unpackU8()
        self.vm_cap["canGetSyntheticAttribute"] = newCapabilityBuf.unpackU8()
        self.vm_cap["canGetOwnedMonitorInfo"] = newCapabilityBuf.unpackU8()
        self.vm_cap["canGetCurrentContendedMonitor"] = newCapabilityBuf.unpackU8()
        self.vm_cap["canGetMonitorInfo"] = newCapabilityBuf.unpackU8()
        self.vm_cap["canRedefineClasses"] = newCapabilityBuf.unpackU8()
        self.vm_cap["canAddMethod"] = newCapabilityBuf.unpackU8()
        self.vm_cap["canUnrestrictedlyRedefineClasses"] = newCapabilityBuf.unpackU8()
        self.vm_cap["canPopFrames"] = newCapabilityBuf.unpackU8()
        self.vm_cap["canUseInstanceFilters"] = newCapabilityBuf.unpackU8()
        self.vm_cap["canGetSourceDebugExtension"] = newCapabilityBuf.unpackU8()        
        self.vm_cap["canRequestVMDeathEvent"] = newCapabilityBuf.unpackU8()        
        self.vm_cap["canSetDefaultStratum"] = newCapabilityBuf.unpackU8()        
        
                
        '''
        self.canWatchFieldModification = newCapabilityBuf.unpackU8()
        self.canWatchFieldAccess = newCapabilityBuf.unpackU8()
        self.canGetBytecodes = newCapabilityBuf.unpackU8()
        self.canGetSyntheticAttribute = newCapabilityBuf.unpackU8()
        self.canGetOwnedMonitorInfo = newCapabilityBuf.unpackU8()
        self.canGetCurrentContendedMonitor = newCapabilityBuf.unpackU8()
        self.canGetMonitorInfo = newCapabilityBuf.unpackU8()
        self.canRedefineClasses = newCapabilityBuf.unpackU8()
        self.canAddMethod = newCapabilityBuf.unpackU8()
        self.canUnrestrictedlyRedefineClasses = newCapabilityBuf.unpackU8()
        self.canPopFrames = newCapabilityBuf.unpackU8()
        self.canUseInstanceFilters = newCapabilityBuf.unpackU8()
        self.canGetSourceDebugExtension = newCapabilityBuf.unpackU8()
        self.canRequestVMDeathEvent = newCapabilityBuf.unpackU8()
        self.canSetDefaultStratum = newCapabilityBuf.unpackU8()
        '''
        
    def __str__(self):  #输出字符串
        dataStr =   "canWatchFieldModification=" + str(self.canWatchFieldModification) + "\r\n"
        dataStr +=   "canWatchFieldAccess=" + str(self.canWatchFieldAccess) + "\r\n"
        dataStr +=   "canGetBytecodes=" + str(self.canGetBytecodes) + "\r\n"
        dataStr +=   "canGetSyntheticAttribute=" + str(self.canGetSyntheticAttribute) + "\r\n"
        dataStr +=   "canGetOwnedMonitorInfo=" + str(self.canGetOwnedMonitorInfo) + "\r\n"
        dataStr +=   "canGetCurrentContendedMonitor=" + str(self.canGetCurrentContendedMonitor) + "\r\n"
        dataStr +=   "canGetMonitorInfo=" + str(self.canGetMonitorInfo) + "\r\n"
        dataStr +=   "canRedefineClasses=" + str(self.canRedefineClasses) + "\r\n"
        dataStr +=   "canAddMethod=" + str(self.canAddMethod) + "\r\n"
        dataStr +=   "canUnrestrictedlyRedefineClasses=" + str(self.canUnrestrictedlyRedefineClasses) + "\r\n"
        dataStr +=   "canPopFrames=" + str(self.canPopFrames) + "\r\n"
        dataStr +=   "canUseInstanceFilters=" + str(self.canUseInstanceFilters) + "\r\n"
        dataStr +=   "canGetSourceDebugExtension=" + str(self.canGetSourceDebugExtension) + "\r\n"
        dataStr +=   "canRequestVMDeathEvent=" + str(self.canRequestVMDeathEvent) + "\r\n"
        dataStr +=   "canSetDefaultStratum=" + str(self.canSetDefaultStratum) + "\r\n"

        
        return dataStr
  

unpack_impl = [None,] * 256

def register_unpack_impl(ek, fn):
    unpack_impl[ek] = fn

def unpack_events(sess, buf):
    sp, ct = buf.unpack('1i')
    for i in range(0, ct):
        ek = buf.unpackU8()
        im = unpack_impl[ek]
        if im is None:
            raise RequestError(ek)
        else:
            yield im(sess, buf)

#处理METHOD_ENTRY事件，对该事件时由虚拟机返回的数据进行解析
def unpack_event_location(sess, buf):
    rid = buf.unpackInt()  #Request that generated event
    t = Thread.unpackFrom(sess, buf)    #thread which entered method。 其中t为一个Thread类型的对象
    loc = Location.unpackFrom(sess, buf) #The initial executable location in the method  其中loc为一个Location类型的对象
    log.debug("study", "in unpack_methode_entry rid=" + str(rid) + "\t thread=" + str(t) + "\t loc=" + str(loc))
    return rid, t, loc

# Breakpoint
register_unpack_impl(2, unpack_event_location)
# MothodEntry
register_unpack_impl(40, unpack_event_location)
# MothodExit
register_unpack_impl(41, unpack_event_location)

class Session(object):
    def __init__(self, conn):
        self.pool = andbug.data.pool()  #在andbug/lib/andbug/data.py文件中定义
        self.conn = conn  #conn是Connection(Thread)的一个对象
        self.emap = {}   #用一个字典来存放hook点的信息，每个元素是一个Hook类型的对象
        self.ectl = Lock()
        self.evtq = Queue()
        conn.hook(0x4064, self.evtq)  #加入evtq队列中 16484  这里是加入命令 0x40 64 转换成十进制是64 100 Event Command Set（64）：Composite Command (100)
        self.ethd = threading.Thread(
            name='Session', target=self.run  #线程的名称，线程的执行函数
        )
        self.ethd.daemon=1  #主线程结束时，会把子线程也杀死。
        self.ethd.start()

    def run(self):
        while True:
            self.processEvent(*self.evtq.get())  #从evtq中取出一个队列，这个的值是在proto.Connection.processRequest函数中被压入队列的

    def hook(self, ident, func = None, queue = None, origin = None):
        return Hook(self, ident, func, queue, origin) #返回的是一个Hook类型的对象

    def processEvent(self, ident, buf):  #关注这里只有两个参数，
        pol, ct = buf.unpack('1i')  #按照格式对数据进行解析， 1表示无符号单字节数值，
        log.debug("study", "in Session.processEvent: ident=" + str(ident) + "\t pol=" + str(pol) + "\t ct=" + str(ct))
        #输出的值为：in Session.processEvent: ident=268435460     pol=1     ct=1
        #其中  pol的值是suspendPolicy，标识暂停的策略，1表示只暂停当前线程， ct表示本次中断所触发的事件数
        for i in range(0,ct):
            ek = buf.unpackU8() #获取事件的类型保存到ek中,ek为jdwp协议中的eventKind
            log.debug("study", "ek="+ str(ek))
            im = unpack_impl[ek] #unpack_impl为定义的全局变量，该变量中保存的是函数,根据eventKind的之，获取对应的事件的处理函数，保存到im中
            if im is None:
                raise RequestError(ek)
            evt = im(self, buf) #调用具体的函数 这里im调用的是unpack_method_entry函数返回的是rid, t, loc三个变量。
            with self.ectl: #请求锁
                hook = self.emap.get(evt[0])
            if hook is not None:  #hook变量的类型是Hook
                hook.put(evt[1:])  #调用Hook类型中的put函数
                          
    def load_classes(self):
        '''
        1、命令  0x01 0x14
        2、注释：释放一系列Object ID的信息列表
        3、[VirtualMachine Command Set ][AllClassesWithGeneric Command (20)]
        '''
		#在这里0x0114分别表示command=0x01和command set=0x14，即VisibleClasses和ClassLoaderReference
        log.debug("study", "call jdwp 0x01 14")
        code, buf = self.conn.request(0x0114, timeout=g_jdwp_request_timeout)
        if code != 0: #如果code不为0，说明发给vm的请求发生错误。
            raise RequestError(code)

        def load_class():
            tag, tid, jni, gen, flags = buf.unpack('1t$$i')  #推测t为thead id 为一个DWORD型，$表示字符串，将数据解析出来
            obj = self.pool(Class, self, tid) #保存相关信息到pool
            obj.tag = tag
            obj.tid = tid
            obj.jni = jni
            obj.gen = gen
            obj.flags = flags
            
            infor = "tag=" + str(tag) + ";\t tid=" + str(hex(tid)) + ";\t jni=" + jni + ";\t gen=" + str(gen) + ";\t flags=" +str(flags);
            log.debug("study",infor)
            
            return obj 
                        
        ct = buf.unpackU32()

        self.classList = andbug.data.view(load_class() for i in range(0, ct))
        self.classByJni = andbug.data.multidict()
        for item in self.classList:
            self.classByJni[item.jni] = item

    classList = defer(load_classes, 'classList')
    classByJni = defer(load_classes, 'classByJni')

    def classes(self, jni=None):
        if jni:
            seq = self.classByJni[jni]
        else:
            seq = self.classList
        return andbug.data.view(seq)
    
    def suspend(self):
        ''''
        1、命令  0x01 0x08
        2、注释：暂停VM
        3、[VirtualMachine Command Set ][Suspend Command (8)]
        '''
        log.debug("study", "call jdwp 0x01 08")
        code, buf = self.conn.request(0x0108, '', g_jdwp_request_timeout)
        if code != 0:
            raise RequestError(code)

    @property
    def count(self):
        ''''
        1、命令  0x01 0x08
        2、注释：似乎有问题
        3、[VirtualMachine Command Set ][Suspend Command (8)]
        '''
        log.debug("study", "call jdwp 0x01 08")
        code, buf = self.conn.request(0x0108, '', g_jdwp_request_timeout)
        if code != 0:
            raise RequestError(code)

    def resume(self):
        ''''
        1、命令  0x01 0x09
        2、注释：暂停VM
        3、[VirtualMachine Command Set ][Resume Command (9)]
        '''
        log.debug("study", "call jdwp 0x01 09")
        code, buf = self.conn.request(0x0109, '', g_jdwp_request_timeout)
        if code != 0:
            raise RequestError(code)

    def exit(self, code = 0):
        ''''
        1、命令  0x01 0x0A
        2、注释：终止VM
        3、[VirtualMachine Command Set ][Exit Command (10)]
        '''
        conn = self.conn
        buf = conn.buffer()
        buf.pack('i', code)
        log.debug("study", "call jdwp 0x01 0A")
        code, buf = conn.request(0x010A, '', g_jdwp_request_timeout)
        if code != 0:
            raise RequestError(code)

    def threads(self, name=None):
        ''''
        1、命令  0x01 0x04
        2、注释：终止VM
        3、[VirtualMachine Command Set ][AllThreads Command (4)]
        '''
        pool = self.pool
        log.debug("study", "call jdwp 0x01 04")
        code, buf = self.conn.request(0x0104, '', g_jdwp_request_timeout)
        if code != 0:
            raise RequestError(code)
        ct = buf.unpackInt()

        def load_thread():
            tid = buf.unpackObjectId()
            return pool(Thread, self, tid)

        seq = (load_thread() for x in range(0,ct))
        if name is not None:
            if rx_dalvik_tname.match(name):
                seq = (t for t in seq if t.name == name)
            else:
                seq = (t for t in seq if t.name.split(' ',1)[-1] == name)
        return andbug.data.view(seq)
    
    
    def vmCapability(self):
        '''
        函数功能：通过调用jdwp指令，获取vm所支持的功能的信息
        注： Capabilities Command (12)
            CapabilitiesNew Command (17)
        '''
        log.debug("study", "call jdwp 0x01 0c Capabilities Command")
        code, buf = self.conn.request(0x010c, '', g_jdwp_request_timeout)
        

        log.debug("study", "call jdwp 0x01 11 CapabilitiesNew Command")
        codeNew, bufNew = self.conn.request(0x0111, '', g_jdwp_request_timeout)
        

        if code!=0:
            raise RequestError(code)
        elif codeNew!=0:
            raise RequestError(codeNew)
        
        vmCapability = VmCapability(buf, bufNew)
        
        return  vmCapability

rx_dalvik_tname = re.compile('^<[0-9]+> .*$')

class Object(Value):
    def __init__(self, sess, oid):
        if oid == 0: raise andbug.errors.VoidError()
        SessionElement.__init__(self, sess)
        self.oid = oid

    def __repr__(self):
        return '<obj %s   %x>' % (self.jni, self.oid)
    
#    def __str__(self):
#        return str(self.fields.values())
    def __str__(self):    
        return str("%s <%s>" % (str(self.jni), str(self.oid)))
    
    def genJson(self):
        '''
        函数功能：为将数据以json格式输出做准备
        参数：无
        返回值：dict或list
        author：anbc
        '''
        data = {}
        data["object_id"] = self.oid
        data["object_type"] = self.jni  
        #data["fields_infor"] = self.fields
        
     
        
          
        fieldInfor={}
        fieldsValue = self.fields
        for k in fieldsValue:
            print k
            fieldInfor[k]=str(fieldsValue[k])
            
        data["fields_infor"] = fieldInfor
        
        return data
        
    @classmethod
    def unpackFrom(impl, sess, buf):
        oid = buf.unpackObjectId()
        # oid = 0 indicates a GC omgfuckup in Dalvik
        # which is NOT as uncommon as we would like..
        log.debug("study", "in unpackFrom oid(object_id)=" + str(oid))
        if not oid: return None         
        log.debug("study", "in unpackFrom impl=" + str(impl))
        return sess.pool(impl, sess, oid) #通过pool方法创建一个String类或Array类的对象，并返回这个对象

    #将oid参数压入jdwp命令的输入参数
    def packTo(self, buf):
        buf.packObjectId(self.oid)

    @property
    def gen(self):
        return self.refType.gen
    
    @property
    def jni(self):
        return self.refType.jni

    def load_refType(self):
        '''
        1、命令  0x09 0x01
        2、注释：返回一个正在运行的对象的引用类型
        3、[ObjectReference Command Set (9)][ReferenceType Command (1)]
        '''
        conn = self.sess.conn
        buf = conn.buffer()
        self.packTo(buf)
        log.debug("study", "call jdwp 0x09 01")
        code, buf = conn.request(0x0901, buf.data(), g_jdwp_request_timeout)
        if code != 0:
            raise RequestError(code)
        self.refType = RefType.unpackFrom(self.sess, buf)
    
    refType = defer(load_refType, 'refType')

    @property
    def fieldList(self):
        r = list(f for f in self.refType.fieldList if not f.static)
        return r

    @property
    def typeTag(self):
        return self.refType.tag

    @property
    def fields(self):
        '''
        1、命令  0x09 0x02
        2、注释：获得成员变量的值
        3、[ObjectReference Command Set (9) ][GetValues Command (2)]
        '''
        sess = self.sess
        conn = self.conn
        buf = conn.buffer()
        buf.packTypeId(self.oid)
        fields = self.fieldList
        buf.packInt(len(fields))
        for field in fields:
            buf.packFieldId(field.fid)
        log.debug("study", "call jdwp 0x09 02")
        code, buf = conn.request(0x0902, buf.data(), g_jdwp_request_timeout)
        if code != 0:
            raise RequestError(code)
        ct = buf.unpackInt()
        vals = {}
        for x in range(ct):
            f = fields[x]
            vals[f.name] = unpack_value(sess, buf)
            log.info("study", "field: %s = %s"%(f.name, vals[f.name]))

        return vals

    def field(self, name):
        sess = self.sess
        conn = self.conn
        buf = conn.buffer()
        buf.packTypeId(self.oid)
        fields = self.fieldList
        buf.packInt(1)

        loc = None
        for i in range(0, len(fields)):
            if fields[i].name == name:
                loc = i
                break
            else:
                continue

        if loc is None:
            return None
        field = fields[loc]
        buf.packFieldId(field.fid)
        code, buf = conn.request(0x0902, buf.data())
        if code != 0:
            raise RequestError(code)
        if buf.unpackInt() != 1:
            return None
        return unpack_value(sess, buf)


    def setField(self, name, value):
        sess = self.sess
        conn = self.conn
        buf = conn.buffer()
        buf.packTypeId(self.oid)
        fields = self.fieldList
        buf.packInt(1)

        loc = None
        for i in range(0, len(fields)):
            if fields[i].name == name:
                loc = i
                break
            else:
                continue

        if loc is None:
            return None
        field = fields[loc]
        buf.packFieldId(field.fid)
        #TODO: WTF: ord(field.jni) !?
        pack_value(sess, buf, value, field.jni[0])
        code, buf = conn.request(0x0903, buf.data())
        if code != 0:
            raise RequestError(code)
        return True

## with andbug.screed.item(str(obj)):
##     if hasattr(obj, 'dump'):
##        obj.dump()

class Array(Object):
    def __repr__(self):
        data = self.getSlice()

        # Java very commonly uses character and byte arrays to express
        # text instead of strings, because they are mutable and have 
        # different encoding implications.

        if self.jni == '[C':
            return repr(''.join(data))
        elif self.jni == '[B':
           
            '''
            #按照buffer实际长度展示
            output=''
            count=0
            len = self.length
            for c in data:                
                if count<len:
                    output +=chr(c)
                count+=1
            '''
            '''
            #原始数据展示，用于后续程序处理            
            output = []
            for c in data:
                output.append(c)
            '''
            
            #展示有效数据
            output=''
            for c in data:
                if c!=0:
                    output +=chr(c)
            
            
            return repr(output)       
            #return repr(''.join(chr(c) for c in data))
        else:
            return repr(data)

    def __getitem__(self, index):
        if index < 0:
            self.getSlice(index-1, index)
        else:
            return self.getSlice(index, index+1)
    
    def __len__(self):
        return self.length
    
    def __iter__(self): return iter(self.getSlice())

    def __str__(self):
       
        return str(self.getSlice())
    
    
    def genJson(self):
        '''
        函数功能：为将数据以json格式输出做准备
        参数：无
        返回值：dict或list
        author：
        '''
        arrayData = self.getSlice()
        data ={}
        
        
        data["array_type"] = self.jni
        data["array_data"] = str(arrayData)
        

        if self.jni == '[B':
            #展示有效数据
            output=''
            for c in arrayData:
                if c>=33 and c<=126:
                    output +=chr(c)
                else:
                    output +="$"
            data["array_data_show"] = str(output)
            
            
        return data
       
           
    @property  #将length方法当作属性使用
    def length(self):
        '''
        1、命令  0x0d 0x01
        2、注释：返回数组的长度
        3、[ArrayReference Command Set (13)][Length Command (1)]
        '''
        conn = self.conn
        buf = conn.buffer()
        self.packTo(buf)  #调用父类Object的方法，获取object id的值
        log.debug("study", "call jdwp 0x0d 01")
        code, buf = conn.request(0x0d01, buf.data(), g_jdwp_request_timeout)        
        if code != 0:
            raise RequestError(code)
        return buf.unpackInt()

    def getSlice(self, first=0, last=-1):
        '''
        1、命令  0x0d 0x02
        2、注释：获得指定数组元素的值，slice 是片段的意思
        3、[ArrayReference Command Set (13)][GetValues Command (2)]
        '''
        length = self.length
        if first > length:
            raise IndexError('first offset (%s) past length of array' % first)
        if last > length:
            raise IndexError('last offset (%s) past length of array' % last)
        if first < 0:
            first = length + first + 1
            if first < 0:
                raise IndexError('first absolute (%s) past length of array' % first)
        if last < 0:
            last = length + last + 1
            if last < 0:
                raise IndexError('last absolute (%s) past length of array' % last)
        if first > last:
            first, last = last, first
        
        count = last - first
        if not count: return []

        conn = self.conn
        buf = conn.buffer()
        self.packTo(buf)  #传入参数object id
        buf.packInt(first) #传入数组的起始位置
        buf.packInt(count) #传入要获取的数组的个数
        log.debug("study", "call jdwp 0x0d 02")
        code, buf = conn.request(0x0d02, buf.data(), g_jdwp_request_timeout)
        if code != 0:
            raise RequestError(code)
        tag = buf.unpackU8()
        ct = buf.unpackInt()
        
        sess = self.sess
        if tag in OBJECT_TAGS:
            return list(unpack_value(sess, buf) for i in range(ct))  #处理对象类型的元素
        else:
            return list(unpack_value(sess, buf, tag) for i in range(ct)) #处理主类型的元素

PRIMITIVE_TAGS = set(ord(c) for c in 'BCFDIJSVZ')
OBJECT_TAGS = set(ord(c) for c in 'stglcL')

#在statics文件的andbug.screed.item("%s = %s" % (k, v))代码中用到vm.String类中的__str__函数，进而调用data(self)发起"call jdwp 0x0A 01"命令
class String(Object):
    def __repr__(self):
        return repr(str(self))

    def __str__(self):
        return self.data  #在这里调用data函数

    def genJson(self):
        return repr(str(self))
    
    
    @property
    def data(self):
        '''
        1、命令  0x0a 0x01
        2、注释：返回一个字符串中包含的字符内容
        3、[StringReference Command Set (10)][Value Command (1)]
        '''
        conn = self.conn
        buf = conn.buffer()
        self.packTo(buf) #将oid参数压入jdwp命令的输入参数
        
        log.debug("study", "buf=" + str(buf))
        log.debug("study", "call jdwp 0x0A 01")
        code, buf = conn.request(0x0A01, buf.data(), g_jdwp_request_timeout)  #需要输入string对象的object id的值
        if code != 0:        
            raise RequestError(code)
        
        return buf.unpackStr()

unpack_value_impl = [None,] * 256

def register_unpack_value(tag, func):
    #print "tag=" +  tag
    #print "func=" + str(func)
    for t in tag:
        log.debug("study", "ord(t)=" + str(ord(t)))
        unpack_value_impl[ord(t)] = func  # ord(t)将字符转换成ascii码

register_unpack_value('B', lambda p, b: b.unpackU8())  #BYTE 'B' - a byte value (1 byte).  
register_unpack_value('C', lambda p, b: chr(b.unpackU16())) #CHAR 'C' - a character value (2 bytes).   
register_unpack_value('F', lambda p, b: b.unpackFloat()) #TODO: TEST  float型
register_unpack_value('D', lambda p, b: b.unpackDouble()) #TODO:TEST  double型
register_unpack_value('I', lambda p, b: b.unpackInt())# int 型
register_unpack_value('J', lambda p, b: b.unpackLong()) #long 型
register_unpack_value('S', lambda p, b: b.unpackShort()) #TODO: TEST short型
register_unpack_value('V', lambda p, b: b.unpackVoid()) #不清楚什么类型
register_unpack_value('Z', lambda p, b: (True if b.unpackU8() else False)) #不清楚什么类型
register_unpack_value('L', Object.unpackFrom)  #对象类型
register_unpack_value('tglc', Object.unpackFrom) #TODO: IMPL
register_unpack_value('s', String.unpackFrom) #字符串型
register_unpack_value('[', Array.unpackFrom) #数组型

def get_variable_type(jni_signature):
    '''
    通过jni_signature的值返回，变量的类型
    '''
    if jni_signature=="[":
        return "ARRAY"
    elif jni_signature=="B":
        return "BYTE"
    elif jni_signature=="C":
        return "CHAR"    
    elif jni_signature=="L":
        return "OBJECT"    
    elif jni_signature=="F":
        return "FLOAT"
    elif jni_signature=="D":
        return "DOUBLE"
    elif jni_signature=="I":
        return "INT"
    elif jni_signature=="J":
        return "LONG"
    elif jni_signature=="B":
        return "BYTE"
    elif jni_signature=="B":
        return "BYTE"


#在函数中根据获取的tag的不同，调用不同的函数进行处理，所有处理函数都保存在unpack_value_impl变量中
#在Array.getSlice函数中，unpack_value函数时传入的tag参数
def unpack_value(sess, buf, tag = None):
    if tag is None: tag = buf.unpackU8()
    fn = unpack_value_impl[tag]
    log.debug("study",  "in unpack_value tag=" + str(tag) + "\t fn=" + str(fn))
    if fn is None:
        raise RequestError(tag)
    else:
        return fn(sess, buf)

pack_value_impl = [None,] * 256
def register_pack_value(tag, func):
    for t in tag:
        pack_value_impl[ord(t)] = func

register_pack_value('B', lambda p, b, v: b.packU8(int(v)))
register_pack_value('F', lambda p, b, v: b.packFloat(float(v))) #TODO: TEST
register_pack_value('D', lambda p, b, v: b.packDouble(float(v))) #TODO:TEST
register_pack_value('I', lambda p, b, v: b.packInt(int(v)))
register_pack_value('J', lambda p, b, v: b.packLong(long(v)))
register_pack_value('S', lambda p, b, v: b.packShort(int(v))) #TODO: TEST
register_pack_value('V', lambda p, b, v: b.packVoid())
register_pack_value('Z', lambda p, b, v: b.packU8(bool(v) and 1 or 0))
#register_pack_value('s', lambda p, b, v: b.packStr(v)) # TODO: pack String

def pack_value(sess, buf, value, tag = None):
    if not tag:
        raise RequestError(tag)
    if isinstance(tag, basestring):
        tag = ord(tag[0])
    print "PACK", repr(tag), repr(value)
    fn = pack_value_impl[tag]
    if fn is None:
        raise RequestError(tag)
    else:
        buf.packU8(tag)
        return fn(sess, buf, value)

def connect(pid, dev=None):
    'connects using proto.forward() to the process associated with this context'
    conn = andbug.proto.connect(andbug.proto.forward(pid, dev))  #conn是Connection(Thread)类型的一个对象
    return andbug.vm.Session(conn)

