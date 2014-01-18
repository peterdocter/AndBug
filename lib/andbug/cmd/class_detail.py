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
def class_detail(ctxt, class_name=None):
    'lists loaded classes. if no partial class name supplied, list all classes.'
    with andbug.screed.section('Loaded Class-detail'):
        
        #classesInfor = ctxt.sess.classes() 
        #print type(classesInfor) classesInfor 的类型是<class 'andbug.data.view'>
        for c in ctxt.sess.classes(): #ctxt.sess.classes()函数来获取类的信息
            #print type(c) 返回的类型是<class 'andbug.vm.Class'>            
            n = c.jni  #获取类中的jni成员变量
            if n.startswith('L') and n.endswith(';'):
                n = n[1:-1].replace('/', '.')
            else:
                continue

            if n==class_name:
                andbug.screed.item(n)                
                
                show_method_infor(c)                
                
                show_static_infor(c)
                
                show_field_infor(c)

def show_method_infor(class_infor):
    '''
    展示指定类中方法的信息
    '''
    andbug.screed.section('Methods Infor:')
    for m in class_infor.methods():
        andbug.screed.item(str(m)) 

def show_static_infor(class_infor):
    '''
    展示类中静态变量的信息
    '''
    andbug.screed.section('Statics Infor:')
    for k, v in class_infor.statics.iteritems():
        andbug.screed.item("%s = %s" % (k, v)) #在这里会到用vm.String类中的__str__函数，进而调用data(self)发起"call jdwp 0x0A 01"命令

def show_field_infor(classinfor):         
    '''
    展示类中成员变量的信息
    '''
    andbug.screed.section('Fields Infor:')
    for field in classinfor.fieldList:
        #print field.get_property()
        #print field.jni
        #print field.name
        #field_str = field.get_property() + " " + str(field.jni) + " "+ str(field.name)
        andbug.screed.item(str(field))
        
        
        