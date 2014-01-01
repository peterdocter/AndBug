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
The andbug.command module underpins the andbug command system by providing 
context and a central registry to command modules in the andbug.cmd package.

Commands for andbug are typically defined as ::

    @andbug.action(
        '<used-argument> [<extra-argument>]'
        (('debug', 'sets the debug level'))
    )
    def sample(ctxt, used, extra=None):
        ...

'''

import os, os.path, sys, getopt, inspect
import andbug.vm, andbug.cmd, andbug.source, andbug.util,andbug.screed
import traceback
from time import sleep
from andbug.errors import *

#TODO: make short_opts, long_opts, opt_table a dynamic parsing derivative.

OPTIONS = (
    ('pid', 'the process to be debugged, by pid or name'),
    ('dev', 'the device or emulator to be debugged (see adb)'),
    ('src', 'adds a directory where .java or .smali files could be found')
)

class Context(object):
    '''
    Commands in AndBug are associated with a command Context, which contains
    options and environment information for the command.  This information
    may be reused for multiple commands within the AndBug shell.
    '''

    def __init__(self):
        self.sess = None
        self.pid = None
        self.dev = None
        self.shell = False  #标识现在是否可以在andbug下运行shell
    
    def connect(self):
        'connects using vm.connect to the process if not already connected'
        if self.sess is not None: return
        self.sess = andbug.vm.connect(self.pid, self.dev)

    #对传入特定命令的参数进行解析
    def parseOpts(self, args, options=OPTIONS, proc=True):
        'parse command options in OPTIONS format'
        short_opts = ''.join(opt[0][0] + ':' for opt in options)  #str: p:d:s:
        long_opts = list(opt[0] + '=' for opt in options)  #list: ['pid=', 'dev=', 'src=']
        opt_table = {}

		#opt_table的值为：
		#	--dev    str: dev
		#	--pid	str: pid
		#	--src	str: src
		#	-d	str: dev
		#	-p	str: pid
		#	-s	str: src
        for opt in options:
            opt_table['-' + opt[0][0]] = opt[0]
            opt_table['--' + opt[0]] = opt[0]

		#分解参数opts保存 参数名参数值的对，  args保存剩余的参数之
		#"xxx.py -h -o file --help --output=out file1 file2" 命令解析后
		#opts的值 [('-h',''),('-o','file'),('--help',''),('--output','out')]
		#args的值 ['file1','file2']
        opts, args = getopt.gnu_getopt(args, short_opts, long_opts)

        opts = list((opt_table[k], v) for k, v in opts) #短命令或长命令变成命令全称
        t = {}
        for k, v in opts: 
            if k == 'src': #处理src命令，猜测是源代码命令
                andbug.source.add_srcdir(v)
            else:
                t[k] = v
        
        if proc:
            pid = t.get('pid')  #获取当前要调试程序的pid的值
            dev = t.get('dev')	#获取当前要调试程序的dev的值
        
            self.findDev(dev)
            self.findPid(pid)

        return args, opts

    def findDev(self, dev=None):
        'determines the device for the command based on dev'
        if self.dev is not None: return  #如果Context对象中dev已经有有效的值了，就不去要再调用获取dev的函数andbug.util.find_dev
        self.dev = andbug.util.find_dev(dev)

    def findPid(self, pid=None):
        'determines the process id for the command based on dev, pid and/or name'        
        if self.pid is not None: return  ##如果Context对象中pid已经有有效的值了，就不去要再调用获取pid的函数andbug.util.find_pid
        cur_pid = andbug.util.find_pid(pid, self.dev)
        count =0
        while cur_pid == None:
            if count%4==0:
                andbug.screed.item("wait......")
                
            sleep(1) #sleep 1秒中后再重新获取pid的值
            count=count+1
            cur_pid = andbug.util.find_pid(pid, self.dev)

            
            if count==60:
                raise OptionError('could not find process ' + str(pid))
        self.pid = cur_pid
        
        
    #判断命令是否可以执行？作用是如果该命令的shell属性为true，那么这个命令就可以直接跟在andbug后
    #作为一个命令直接运行
    def can_perform(self, act):
        'uses the act.shell property to determine if it makes sense'
        if self.shell:
            return act.shell != False  #值不等于true返回false
        return act.shell != True  #值不等于false，返回true

    def block_exit(self):
        'prevents termination outside of shells'

        if self.shell:
            # we do not need to block_exit, readline is doing a great
            # job of that for us.
            return

        while True:
            # the purpose of the main thread becomes sleeping forever
            # this is because Python's brilliant threading model only
            # allows the main thread to perceive CTRL-C.
            sleep(3600)
        

    #函数功能：执行具体命令
    #参数：	cmd 具体要执行的命令
    #		args 命令的参数
    def perform(self, cmd, args):
        'performs the named command with the supplied arguments'
        act = ACTION_MAP.get(cmd) #获取对应命令的处理函数

        if not act:
            perr('!! command not supported: "%s."' % cmd)
            return False

        if not self.can_perform(act): #函数返回false退出
            if self.shell:
                perr('!! %s is not available in the shell.' % cmd)
            else:
                perr('!! %s is only available in the shell.' % cmd)
            return False

        #具体解析，当前命令的参数
        args, opts = self.parseOpts(args, act.opts, act.proc)
        argct = len(args) + 1 

        if argct < act.min_arity:  #如果小于最小的参数个数，退出
            perr('!! command "%s" requires more arguments.' % cmd)
            return False
        elif argct > act.max_arity:#如果大于最大的参数个数，退出
            perr('!! too many arguments for command "%s."' % cmd)
            return False

        opts = filter(lambda opt: opt[0] in act.keys, opts)
        kwargs  = {}
        for k, v in opts: 
            kwargs[k] = v

        if act.proc: self.connect()
        try:
            act(self, *args, **kwargs)
        except Exception as exc:
            dump_exc(exc)
            return False

        return True

def dump_exc(exc):       
    tp, val, tb = sys.exc_info()
    with andbug.screed.section("%s: %s" % (tp.__name__, val)):
        for step in traceback.format_tb(tb):
            step = step.splitlines()
            with andbug.screed.item(step[0].strip()):
                for line in step[1:]:
                    andbug.screed.line(line.strip())

ACTION_LIST = []
ACTION_MAP = {}

#具体实现将命令信息保存到List、Map中
def bind_action(name, fn, aliases):
    ACTION_LIST.append(fn)
    ACTION_MAP[name] = fn
    for alias in aliases:
        ACTION_MAP[alias] = fn

def action(usage, opts = (), proc = True, shell = None, name = None, aliases=()):
    'decorates a command implementation with usage and argument information'
    def bind(fn):
        fn.proc = proc
        fn.shell = shell
        fn.usage = usage   #使用方法
        fn.opts = OPTIONS[:] + opts   #当前命令的参数有哪些
        fn.keys = list(opt[0] for opt in opts) #保存的短命令的值
        fn.aliases = aliases    #当前命令的别名
        spec = inspect.getargspec(fn)   #功能是获取函数fn所定义的参数名称，对fn进行解析，计算出参数的个数，和有默认值参数的个数，从而计算出每个命令最多需要多少个参数，最少需要多少个参数
                                        #仅用于方法，获取方法声明的参数，返回元组，分别是(普通参数名的列表, *参数名, **参数名, 默认值元组)。如果没有值，将是空列表和3个None。如果是2.6以上版本，将返回一个命名元组(Named Tuple)，即除了索引外还可以使用属性名访问元组中的元素。
        defct = len(spec.defaults) if spec.defaults else 0
        argct = len(spec.args) if spec.args else 0
        fn.min_arity = argct - defct   #当前命令，允许的最小参数个数
        fn.max_arity = argct	##当前命令，允许的最大参数个数
        fn.name = name or fn.__name__.replace('_', '-')

        bind_action(fn.name, fn, aliases)
    return bind

CMD_DIR_PATH = os.path.abspath(os.path.join( os.path.dirname(__file__), "cmd" )) #该变量保存的路径为"~/andbug/lib/andbug/cmd"

#将cmd目录下，所有*.py文件都import进来，动态加载模块的程序中的一个过程
def load_commands():
    'loads commands from the andbug.cmd package'  
    for name in os.listdir(CMD_DIR_PATH):
        if name.startswith( '__' ):
            continue
        if name.endswith( '.py' ):
            name = 'andbug.cmd.' + name[:-3]
            try:
                __import__( name )  #动态导入其他模块，这是会执行，指定python文件中的@andbug.command.action函数
            except andbug.errors.DependencyError:
                pass # okay, okay..


#执行调试命令，每个调试命令都从这个函数开始
#参数:	args 命令的名称以及相关参数
#	ctxt = None   用于支持命令执行的类成员，细节未知
def run_command(args, ctxt = None):
    'runs the specified command with a new context'
    if ctxt is None:
        ctxt = Context()
            
    for item in args:
        if item in ('-h', '--help', '-?', '-help'):
            args = ('help', args[0])
            break
    
    return ctxt.perform(args[0], args[1:])

#定义本文件向其他文件可以到处的函数、变量的名称
__all__ = (
    'run_command', 'load_commands', 'action', 'Context', 'OptionError'
)



'''
inspect.getargspec(fn) 函数的使用

在example.py文件中
def module_level_function(arg1, arg2='default', *args, **kwargs):
	#This function is declared in the module.
	local_variable = arg1

在use_inspect文件中
import inspect
import example

argspec = inspect.getargspec(example.module_level_function)
print 'Names', argsec[0]
print '*：'， argspec[1]
print '**:', argspec[2]
print 'default:', argspec[3]
arg_with_defaults= argspec[0][-len(argspec[3]):]
print 'arg & defaults:', zip(arg_with_defaults, argspec[3])

运行后的结果：
Names: ['arg1', 'arg2']
*: args
**: kwargs
default: ('default',)
arg & defaults: [('arg2', 'default')]



'''
