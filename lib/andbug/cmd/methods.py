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

'implementation of the "methods" command'

import andbug.command, andbug.options
from andbug import log

@andbug.command.action('<class-path> [<method-query>]')
def methods(ctxt, cpath, mquery=None):
    'lists the methods of a class'
    cpath, mname, mjni = andbug.options.parse_mquery(cpath, mquery)  #cpath=Lcom/example/test/MainActivity;     mname=onCreate [函数名]  mjni=None［可能是参数信息不确定］ 
    infor = "cpath="+ str(cpath) + "\t mname="+ str(mname) + "\t mjni=" + str(mjni);            
    log.debug("study", infor);
    
    
    title = "Methods " + ((cpath + "->" + mquery) if mquery else (cpath))
    with andbug.screed.section(title):
        for m in ctxt.sess.classes(cpath).methods(name=mname, jni=mjni):
            #str(m) 类似如下信息com.example.test.MainActivity.onCreate(Landroid/os/Bundle;)V  m值的类型是<class 'andbug.vm.Method'>
            andbug.screed.item(str(m)) 

