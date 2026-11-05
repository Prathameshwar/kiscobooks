import assert from "node:assert/strict";
import test from "node:test";
import {createReportsClient} from "../src/index.ts";
test("report run retries retain identity and pin the requested source generation",async()=>{
 const requests=[];
 const client=createReportsClient({baseUrl:"https://gateway.example.test/reports",fetch:async request=>{
   requests.push({path:new URL(request.url).pathname,key:request.headers.get("Idempotency-Key"),body:await request.json()});
   return Response.json({id:"run",status:"PENDING",generation_id:"generation"},{status:202});
 }});
 const command={params:{path:{company_id:"company"},header:{"Idempotency-Key":"stable-run"}},body:{code:"SOURCE_RECONCILIATION",generation_id:"generation"}};
 await client.POST("/v1/companies/{company_id}/report-runs",command);
 await client.POST("/v1/companies/{company_id}/report-runs",command);
 assert.deepEqual(requests.map(row=>row.key),["stable-run","stable-run"]);
 assert.equal(requests[0].body.generation_id,"generation");
 assert.equal(requests[0].path,"/reports/v1/companies/company/report-runs");
});
