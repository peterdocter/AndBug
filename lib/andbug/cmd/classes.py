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

'implementation of the "classes" command'

import andbug.command, andbug.screed
import types

@andbug.command.action('[<partial class name>]')
def classes(ctxt, expr=None):
    'lists loaded classes. if no partial class name supplied, list all classes.展示一个类的详情'
    with andbug.screed.section('Loaded Classes'):
        
        #classesInfor = ctxt.sess.classes() 
        #print type(classesInfor) classesInfor 的类型是<class 'andbug.data.view'>
        for c in ctxt.sess.classes(): #ctxt.sess.classes()函数来获取类的信息
            #print type(c) 返回的类型是<class 'andbug.vm.Class'>            
            n = c.jni  #获取类中的jni成员变量
            if n.startswith('L') and n.endswith(';'):
                n = n[1:-1].replace('/', '.')
            else:
                continue

            if expr is not None:
                #通过正则判断要输出的类信息
                if n.find(expr) >= 0:
                    andbug.screed.item(n)
            else:
                andbug.screed.item(n)
            
