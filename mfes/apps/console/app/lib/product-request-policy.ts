import {allowedVoucherRequest} from './voucher-request-policy';
import {allowedSimpleProductRequest} from './simple-product-policy';
import {allowedStockRequest} from './stock-policy';
import {allowedStockTrackingRequest, allowedActivatedStockProfileRead} from './stock-tracking-policy';
import {allowedProductCreationRequest} from './product-creation-policy';
import {allowedMoneyRequest} from './money-request-policy';
import {allowedCatalogMasterRequest} from './catalog-master-policy';
import {allowedTaxRequest} from './tax-request-policy';
import {allowedDesignRequest} from './design-request-policy';
import {allowedWarehouseStructureRequest} from './warehouse-structure-policy';
import {allowedUnitsIdentifiersRequest} from './units-identifiers-policy';
import {allowedAttributeRequest} from './attribute-request-policy';
import {allowedPricingRequest} from './pricing-request-policy';
import {allowedProductProfileRequest} from './product-profile-request-policy';
import {allowedPromotionStackRequest} from './promotion-stack-policy';
import {allowedBomRequest} from './bom-request-policy';
import {allowedClassificationRequest} from './product-classification-policy';
import {allowedWarehouseAction, allowedWarehouseIdentityLookup} from './warehouse-request-policy';
import {allowedConfigurationRequest} from './product-configuration-policy';
import {allowedAccountingConfigurationRequest, allowedAccountingIdentityLookup, allowedAccountingCatalogLookup} from './accounting-configuration-policy';
const id = '[0-9a-f-]{36}';
const product = '(?:catalog[.]item|catalog[.]product_family)';
export function allowedProductRequest(service: string, method: string, path: string): boolean {
  const route = path.split('?')[0];
  if (route.includes('\\') || route.includes('..') || path.includes('#') || /%2f|%5c/i.test(route)) return false;
  if (service === 'identity') {
    if(new RegExp('^/v1/companies/'+id+'/gst-filing-preferences$','i').test(route))return ['GET','POST'].includes(method)&&route===path;
    if(new RegExp('^/v1/companies/'+id+'/gst-filing-preferences/'+id+'$','i').test(route))return method==='PATCH'&&route===path;
    if (allowedAccountingIdentityLookup(method, path)) return true;
    if (allowedWarehouseIdentityLookup(method, path)) return true;
    if (/^\/v1\/reference\/(countries|timezones|countries\/[A-Z]{2}\/states)$/.test(route)) return method === 'GET' && route === path;
    if (route === '/v1/custom-field-definitions') return ['GET','POST'].includes(method);
    if (new RegExp('^/v1/custom-field-definitions/'+id+'$','i').test(route)) return ['GET','PUT'].includes(method);
    return method === 'GET' && new RegExp('^/v1/entities/'+product+'/custom-field-contract$').test(route);
  }
  if (service === 'vouchers') return allowedVoucherRequest(method,path);
  // Document layout: its own namespace, and nothing else in this route serves it, so an
  // unrecognised design path is refused here rather than judged by catalog's rules.
  if (service === 'design') return allowedDesignRequest(method, path) === true;
  if (service === 'accounting') {
    const stock = allowedStockRequest(method, path);
    if (stock !== undefined) return stock;
    const tracking = allowedStockTrackingRequest(method, path);
    if (tracking !== undefined) return tracking;
    const configuration = allowedAccountingConfigurationRequest(method, path);
    if (configuration !== undefined) return configuration;
  }
  if (service === 'accounting'||service === 'reports') return allowedMoneyRequest(service,method,path);
  if (service !== 'catalog') return false;
  // Configuration owns its option paths before resource-name policies inspect them.
  const configuration = allowedConfigurationRequest(method, path);
  if (configuration !== undefined) return configuration;
  const simple = allowedSimpleProductRequest(method, path);
  if (simple !== undefined) return simple;
  if (allowedActivatedStockProfileRead(method, path)) return true;
  const stack = allowedPromotionStackRequest(method, path);
  if (stack !== undefined) return stack;
  const bom = allowedBomRequest(method, path);
  if (bom !== undefined) return bom;
  const profiles = allowedProductProfileRequest(method, path);
  if (profiles !== undefined) return profiles;
  const pricing = allowedPricingRequest(method, path);
  const creation = allowedProductCreationRequest(method, path);
  if (creation !== undefined) return creation;
  if (pricing !== undefined) return pricing;
  const attributes = allowedAttributeRequest(method, path);
  if (attributes !== undefined) return attributes;
  const classification = allowedClassificationRequest(method, path);
  if (classification !== undefined) return classification;
  const units = allowedUnitsIdentifiersRequest(method, path);
  if (units !== undefined) return units;
  if (allowedAccountingCatalogLookup(method, path)) return true;
  const structure = allowedWarehouseStructureRequest(method, path);
  if (structure !== undefined) return structure;
  const tax = allowedTaxRequest(method, path);
  if (tax !== undefined) return tax;
  const warehouse = allowedWarehouseAction(method, path);
  if (warehouse !== undefined) return warehouse;
  const master = allowedCatalogMasterRequest(method, path);
  if (master !== undefined) return master;
  const prefix = '^/v1/companies/'+id;
  if (new RegExp(prefix+'/barcodes/resolve$','i').test(route)) return method === 'POST';
  if (new RegExp(prefix+'/items/'+id+'/quantity-preview$','i').test(route)) return method === 'POST' && !path.includes('?');
  if (new RegExp(prefix+'/attribute-(?:definitions|options|sets)(?:/'+id+'(?:/(?:activate|deactivate))?)?$','i').test(route)) {
    const lifecycle=/(?:activate|deactivate)$/.test(route), detail=new RegExp('/'+id+'$','i').test(route);
    return lifecycle ? method==='POST' : detail ? ['GET','PATCH'].includes(method) : ['GET','POST'].includes(method);
  }
  if (new RegExp(prefix+'/items/'+id+'/attribute-form$','i').test(route)) return method==='GET';
  if (new RegExp(prefix+'/(?:items|product-families)/'+id+'/attributes$','i').test(route)) return ['GET','PUT'].includes(method);
  if (new RegExp(prefix+'/product-families/'+id+'/variants$','i').test(route)) return method==='POST';
  if (new RegExp(prefix+'/entities/catalog[.](?:attribute_definition|attribute_option|family_attribute|family_attribute_option|item_attribute_value)/field-set$','i').test(route)) return method==='GET';

  if (new RegExp(prefix+'/(?:items|product-families)(?:/'+id+')?$','i').test(route)) return method === 'GET' || (method === 'PATCH' && new RegExp('/'+id+'$','i').test(route));
  if (new RegExp(prefix+'/entities/'+product+'/field-set$','i').test(route)) return method === 'GET';
  if (new RegExp(prefix+'/entities/'+product+'/custom-field-adoption(?:/preview)?$','i').test(route)) return method === 'POST';
  return method === 'GET' && new RegExp(prefix+'/option-sources/catalog\\.[a-z_]+$','i').test(route);
}
