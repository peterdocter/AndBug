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

'implementation of the "break" command'

import andbug.command, andbug.screed, andbug.options
from Queue import Queue

def parse_frame_detail(frame):
    '''
    函数功能：解析一个堆栈帧的详细情况
    '''
    all_var_infor = frame.values
    for var_name in all_var_infor:
        #print "%s = %s" %(var_name, all_var_infor[var_name])
        andbug.screed.item(var_name + ":" + str(all_var_infor[var_name]))

def report_hit(t):
    '''
    处理METHOD_ENTRY事件回调函数，
    t有两个参数，分别  t[0] thread
                    t[1] Location
    '''
    t = t[0] #t是一个Thread类型的变量
    with andbug.screed.section("Breakpoint hit in %s, process suspended." % t):
        #t.sess.suspend() #暂停当前线程
        count = 10 if len(t.frames) > 10 else len(t.frames)
        for f in t.frames[0: count]:
            name = str(f.loc)
            if f.native:  #判断堆栈中函数的类型，是否是内部函数。如dalvik.system.NativeStart.main([Ljava/lang/String;)V <native>
                name += ' <native>'
            andbug.screed.item(name)

def cmd_break_methods(ctxt, cpath, mpath):
    for c in ctxt.sess.classes(cpath):
        for m in c.methods(mpath):
            l = m.firstLoc   #这里会调用jdwp的命令
            if l.native:  #等于true，无法设置断点
                andbug.screed.item('Could not hook native %s' % l)
                continue
            h = l.hook(func = report_hit)
            andbug.screed.item('Hooked %s' % h)

def cmd_break_classes(ctxt, cpath):
    for c in ctxt.sess.classes(cpath): #c为vm.py中，Class类的一个对象
        h = c.hookEntries(func = report_hit)
        andbug.screed.item('Hooked %s' % h)

def cmd_break_line(ctxt, cpath, mpath, line):
    for c in ctxt.sess.classes(cpath):
        for m in c.methods(mpath):
            l = m.lineTable
            if l is None or len(l) <= 0:
                continue
            if line == 'show':
                andbug.screed.item(str(sorted(l.keys())))
                continue
            l = l.get(line, None)
            if l is None:
                andbug.screed.item("can't found line %i" % line)
                continue
            if l.native:
                andbug.screed.item('Could not hook native %s' % l)
                continue
            h = l.hook(func = report_hit)
            andbug.screed.item('Hooked %s' % h)

@andbug.command.action(
    '<class> [<method>] [show/lineNo]', name='break', aliases=('b',), shell=True
)
def cmd_break(ctxt, cpath, mquery=None, line=None):
    'set breakpoint'
    cpath, mname, mjni = andbug.options.parse_mquery(cpath, mquery)
    #print "cpath=" + cpath + "\t mname=" + mname + "\t mjni=" + mjni 
    #输出的结果是：cpath=Lcom/example/test/MainActivity$1;     mname=onClick     mjni=(Landroid/view/View;)V
    if line is not None:
        if line != 'show':
            line = int(line)

    with andbug.screed.section('Setting Hooks'):
        if mname is None:
            cmd_break_classes(ctxt, cpath)
        elif line is None:
            cmd_break_methods(ctxt, cpath, mname)
        else:
            cmd_break_line(ctxt, cpath, mname, line)

    ctxt.block_exit()
