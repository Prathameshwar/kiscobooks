import assert from "node:assert/strict";
import test from "node:test";
import {createVouchersClient} from "../src/index.ts";
test("voucher transport preserves exact quantities and stable retry identity", async()=>{
  const requests=[];
  const client=createVouchersClient({baseUrl:"https://gateway.example.test/vouchers",fetch:async request=>{
    requests.push({key:request.headers.get("Idempotency-Key"),body:await request.json(),path:new URL(request.url).pathname});
    return Response.json({id:"document",revision_id:"revision",row_version:1},{status:201});
  }});
  const command={params:{path:{company_id:"company"},header:{"Idempotency-Key":"same-command"}},body:{type_revision_id:"type",document_date:"2026-04-01",currency:"INR",mode:"ITEMS",lines:[{line_key:"line",item:{item_id:"sku",item_version:1,unit_id:"unit",actual_quantity:"11.0000",billed_quantity:"10.0000"}}]}};
  await client.POST("/v1/companies/{company_id}/vouchers",command);
  await client.POST("/v1/companies/{company_id}/vouchers",command);
  assert.deepEqual(requests.map(r=>r.key),["same-command","same-command"]);
  assert.equal(requests[0].body.lines[0].item.actual_quantity,"11.0000");
  assert.equal(requests[0].path,"/vouchers/v1/companies/company/vouchers");
});
