'use client';
import {GstReturnWorkspace} from './Gstr3bWorkspace';
export function Gstr1Workspace(props:{company:string;permissions:readonly string[]}){
 return <GstReturnWorkspace {...props} report="GSTR1"/>;
}
