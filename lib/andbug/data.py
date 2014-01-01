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


#这个模块可以单独测试以搞清楚实现原理



from threading import Lock

class multidict(dict):
    '''
    boring old multidicts..
    '''
    def get(self, key, alt=[]):
        return dict.get(self, key, alt)
    
    def put(self, key, val):
        try:
            dict.__getitem__(self, key).append(val)
        except KeyError:
            v = view()
            v.append(val)
            dict.__setitem__(self, key, v)
 
    def __setitem__(self, key, val):  #用于对应字典的[]操作符
        self.put(key, val)
    
    def __getitem__(self, key):
        return self.get(key)

class pool(object):
    '''
    a pool of singleton[单独的] objects such that, for any combination[联合体] of constructor 
    and 1 or more initializers, there may be zero or one objects; attempting
    to reference a nonexisted object causes it to be created.

    example:
        def t(a): return [a,0]
        p = pool()
        t1 = p(t,1)
        t2 = p(t,2)
        p(t,1)[1] = -1
        # t1[1] is now -1, not 1
    '''
    def __init__(self):
        self.pools = {}
        self.lock = Lock()
	
	#调用方式：return pool(classitem, self.cid)
    def __call__(self, *ident):  #调用方式：m1 = pool(methoditem, 'c1', 'm1')  
        with self.lock:
            pool = self.pools.get(ident)
            if pool is None:
                pool = ident[0](*ident[1:])  #这里会出现什么样的运算结果还不清楚
                self.pools[ident] = pool
            return pool
    '''
对def __call__(self, *ident)函数的调用方式obj = self.pool(Class, self, tid)
增加下面调试信息：
                print "ident[0]="+str(ident[0])
                print type(ident[0])
                print "ident[1]="+str(ident[1]) 
                print type(ident[1])
                print "ident[2]="+str(ident[2]) 
                print type(ident[2])
可以获得如下调试内容
ident[0]=<class 'andbug.vm.Class'>
<type 'type'>
ident[1]=<andbug.vm.Session object at 0x87eb20c>
<class 'andbug.vm.Session'>
ident[2]=834311174200
<type 'long'>

    '''
			
#使用方式：v = view((m1,m2,m3))
class view(object):
    '''
    a homogenous[同类的] collection[采集] of objects that may be acted upon in unison, such
    that calling a method on the collection with given arguments would result
    in calling that method on each object and returning the results as a list
    '''

    def __init__(self, items = []):
        self.items = list(items)
    def __repr__(self):  #字符串重复
        return '(' + ', '.join(str(item) for item in self.items) + ')'
    def __len__(self):
        return len(self.items)
    def __getitem__(self, index):
        return self.items[index]
    def __iter__(self):
        return iter(self.items)
    def __getattr__(self, key): #当属性没有找到时调用 
        def poolcall(*args, **kwargs):
            t = tuple( 
                getattr(item, key)(*args, **kwargs) for item in self.items
            )
            for n in t:
                if not isinstance(n, view):
                    return view(t)
            return view(flatten(t))
        poolcall.func_name = '*' + key
        return poolcall
    
    
    def get(self, key):
        '''
            descript:通过对list中的每个成员调用getattr函数，实现将所有信息检索出来
        '''
        return view(getattr(item, key) for item in self.items)
    def set(self, key, val):
        for item in self.items:
            setattr(item, key, val)
    def append(self, val):
        self.items.append(val)

#函数功能：将二维的数组，展开成一维数组
def flatten(seq):
    for ss in seq:
        for s in ss:
            yield s
			
#？推迟延期			
#具体调用方式是：first = defer(load_line_table, 'first')
def defer(func, name):
    '''
    a property【性质】 decorator【装饰者】 that, when applied, specifies a property that relies
    on the execution of a costly function for its resolution; this permits the
    deferral of evaluation until the first time it is needed.

    unlike other deferral implementation, this one accepts the reality that the
    product of a single calculation may be multiple properties
    '''
    def fget(obj, type=None):   
        try:
            return obj.props[name]  #按照指定的要求取元素，一旦获取失败就处罚异常，于是执行下面的func(obj)函数
        except KeyError:
            pass
        except AttributeError:
            obj.props = {}

        obj.props[name] = None
        func(obj)
        return obj.props[name]
    
    def fset(obj, value):
        try:
            obj.props[name] = value
        except AttributeError:
            obj.props = {name : value}

    fget.func_name = 'get_' + name  #func_name 没能找到相关资料
    fset.func_name = 'set_' + name
    return property(fget, fset)  #设置当获取值时调用fget函数，当设置值是调用fset函数

	
#下面应该都是用于测试的代码
if __name__ == '__main__':
    pool = pool()

    class classitem:
        def __init__(self, cid):
            self.cid = cid
        def __repr__(self):
            return '<class %s>' % self.cid

    class methoditem:
        def __init__(self, cid, mid):
            self.cid = cid
            self.mid = mid
        def __repr__(self):
            return '<method %s:%s>' % (self.cid, self.mid)
        def classitem(self):
            return pool(classitem, self.cid)
        def load_line_table(self):
            print "LOAD-LINE-TABLE", self.cid, self.mid
            self.first = 1
            self.last = 1
            self.lines = []
        def trace(self): #跟踪的意思
            print "TRACE", self.cid, self.mid

        first = defer(load_line_table, 'first')
        last =  defer(load_line_table, 'last')
        lines = defer(load_line_table, 'lines')

    m1 = pool(methoditem, 'c1', 'm1')
    m2 = pool(methoditem, 'c1', 'm2')
    m3 = pool(methoditem, 'c2', 'm3')
    v = view((m1,m2,m3))
    print v
    print v.trace
    print v.trace()
    print (v.get('first'))
    print (v.get('last'))
    print v.classitem()
    print list(m for m in v)
