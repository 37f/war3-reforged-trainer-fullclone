/* R26 isolated local-camera command. No unit access, orders or task setters. */
static DWORD war3_quest_camera(NativeCommand *cmd,NativeOp *op) {
    if(cmd->unit_handle || cmd->reserved || cmd->op_count!=1 || op->rawcode || op->handler || !op->arg1)
        return ERROR_INVALID_PARAMETER;
    uint32_t bits[2]={(uint32_t)op->arg0,(uint32_t)(op->arg0>>32)};
    float x,y,duration=0.25f;memcpy(&x,&bits[0],4);memcpy(&y,&bits[1],4);
    if(!(x==x) || !(y==y) || x< -1000000.f || x>1000000.f || y< -1000000.f || y>1000000.f)
        return ERROR_INVALID_PARAMETER;
    DWORD error=ERROR_INVALID_DATA;
    __try {
        /* The existing active-map query guards menus, reloads and stale clicks. */
        NativeCommand check={0};NativeOp query={0};uint64_t *header=NULL;uint32_t count=0;
        check.op_count=1;query.kind=WAR3_NATIVE_OP_EXT_QUERY_CATALOG_HEADER;
        error=war3_catalog_query(&check,&query,&header,&count);
        if(!error && (count!=6 || header[2]!=op->arg1))error=ERROR_RETRY;
        if(header)HeapFree(GetProcessHeap(),0,header);
        if(error)__leave;
        uint8_t *image,*table;uint64_t handler=0;
        if((error=war3_bootstrap_context(&image,&table)))__leave;
        int index=war3_bootstrap_index("PanCameraToTimed");
        if(index<0) {error=ERROR_PROC_NOT_FOUND;__leave;}
        if((error=war3_bootstrap_query(image,table,(uint32_t)index,&handler)))__leave;
        typedef void (__fastcall *CameraFn)(const float *,const float *,const float *);
        ((CameraFn)(uintptr_t)handler)(&x,&y,&duration);
        op->result=op->arg0;
    } __except(EXCEPTION_EXECUTE_HANDLER) {error=GetExceptionCode();}
    return error;
}
