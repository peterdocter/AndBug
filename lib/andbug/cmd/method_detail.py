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

'implementation of the "methods-detail" command'

import andbug.command, andbug.options
from andbug import log

@andbug.command.action('<class-path> [<method-query>]')
def method_detail(ctxt, cpath, mquery=None):
    '获取一个指定成员函数的详细信息'
    cpath, mname, mjni = andbug.options.parse_mquery(cpath, mquery)  #cpath=Lcom/example/test/MainActivity;     mname=onCreate [函数名]  mjni=None［可能是参数信息不确定］ 
    #infor = "cpath="+ str(cpath) + "\t mname="+ str(mname) + "\t mjni=" + str(mjni);            
    log.debug("study", infor );
  
    if mname==None:
        andbug.screed.item("please Input methods name")  
        return
    
    title = "Methods " + ((cpath + "->" + mquery) if mquery else (cpath))
    with andbug.screed.section(title):
        for m in ctxt.sess.classes(cpath).methods(name=mname, jni=mjni):

            with andbug.screed.section('Method Detail:'):
                 andbug.screed.text(str(m)) 
                 
            andbug.screed.section("LOCATION:")                 
            andbug.screed.item("firstLoc=%s  line=%s" %(m.firstLoc.loc, m.firstLoc.line) )                 
            andbug.screed.item("lastLoc=%s" %(m.lastLoc.loc) )
            with andbug.screed.item("lineTable infor:"):
                for lineItem in m.lineTable:
                    andbug.screed.item("loc=%s  line=%s" %(m.lineTable[lineItem].loc, lineItem ))
            
             
            
            thisIndex=0
            for arg in m.slots:
                thisIndex= thisIndex+1
                if arg.name=="this":
                   break
              
            thisIndex= thisIndex-1 
            andbug.screed.section("ARGUMENT:")  
            for i in range(thisIndex, m.slot_cnt):                
                arg = m.slots[i]
                if arg.jni[0]=='L':
                    andbug.screed.item(arg.jni[1:-1]+ "  " +arg.name) 
                else:
                    andbug.screed.item(andbug.vm.get_variable_type(arg.jni) + "  " +arg.name)
            
            andbug.screed.section("VARIABLE:")
            for i in range(0, thisIndex):                
                arg = m.slots[i]
                if arg.jni[0]=='L':
                    andbug.screed.item(arg.jni[1:-1]+ "  " +arg.name) 
                else:
                    andbug.screed.item(andbug.vm.get_variable_type(arg.jni) + "  " +arg.name)
            
          
                
                
                
                
                
                
                
                
                
                
                
                
                
                
                
                
                
                
                
                
                
                
                
                