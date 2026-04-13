import fs from "fs";
import path from "path";
import { PROJECT_ROOT } from "./config.js";

class SchemaValidator {
  constructor() {
    this.schemas = new Map();
    this.messageSchema = null;
    this.loadSchemas();
  }

  loadSchemas() {
    const schemasDir = path.join(PROJECT_ROOT, "schemas");

    const messageSchemaPath = path.join(schemasDir, "message.json");
    if (fs.existsSync(messageSchemaPath)) {
      this.messageSchema = JSON.parse(fs.readFileSync(messageSchemaPath, "utf8"));
    }

    const portSchemasPath = path.join(schemasDir, "ports.json");
    if (fs.existsSync(portSchemasPath)) {
      const portSchemas = JSON.parse(fs.readFileSync(portSchemasPath, "utf8"));
      if (portSchemas.definitions && typeof portSchemas.definitions === "object") {
        Object.entries(portSchemas.definitions).forEach(([key, schema]) => {
          this.schemas.set(key, schema);
        });
      }
    }
  }

  validateMessage(message) {
    if (!this.messageSchema) {
      return { valid: true, errors: [] };
    }

    const errors = this.validateObject(message, this.messageSchema, "message");
    return {
      valid: errors.length === 0,
      errors
    };
  }

  validatePayload(payload, port) {
    const schemaType = this.getSchemaTypeFromPort(port);
    if (!schemaType || !this.schemas.has(schemaType)) {
      return { valid: true, errors: [] };
    }

    const schema = this.schemas.get(schemaType);
    const errors = this.validateObject(payload, schema, "payload");
    return {
      valid: errors.length === 0,
      errors
    };
  }

  getSchemaTypeFromPort(port) {
    const portToSchema = {
      "command.in": "command",
      "command.out": "command",
      "plan.in": "plan",
      "plan.out": "plan",
      "result.in": "result",
      "result.out": "result",
      "event.in": "event",
      "event.out": "event",
      "query.in": "memory_query",
      "memory.out": "memory_data",
      "request.in": "approval_request",
      "response.out": "approval_response"
    };

    return portToSchema[port] || null;
  }

  validateObject(obj, schema, pathName = "object") {
    const errors = [];

    if (typeof obj !== "object" || obj === null || Array.isArray(obj)) {
      errors.push(`${pathName}: expected object`);
      return errors;
    }

    if (!schema || typeof schema !== "object") {
      return errors;
    }

    if (Array.isArray(schema.required)) {
      for (const prop of schema.required) {
        if (!(prop in obj)) {
          errors.push(`${pathName}: missing required property '${prop}'`);
        }
      }
    }

    if (schema.properties && typeof schema.properties === "object") {
      for (const [prop, propSchema] of Object.entries(schema.properties)) {
        if (prop in obj) {
          const value = obj[prop];
          const propErrors = this.validateValue(
            value,
            propSchema,
            `${pathName}.${prop}`
          );
          errors.push(...propErrors);
        }
      }
    }

    if (schema.additionalProperties === false) {
      for (const prop of Object.keys(obj)) {
        if (!schema.properties || !(prop in schema.properties)) {
          errors.push(`${pathName}: unexpected property '${prop}'`);
        }
      }
    }

    return errors;
  }

  validateValue(value, schema, propName) {
    const errors = [];

    if (!schema || typeof schema !== "object") {
      return errors;
    }

    if (schema.type) {
      const expectedType = schema.type;
      const actualType = Array.isArray(value)
        ? "array"
        : value === null
          ? "null"
          : typeof value;

      if (Array.isArray(expectedType)) {
        if (!expectedType.includes(actualType)) {
          errors.push(
            `${propName}: expected type ${expectedType.join("|")}, got ${actualType}`
          );
          return errors;
        }
      } else if (actualType !== expectedType) {
        errors.push(`${propName}: expected type ${expectedType}, got ${actualType}`);
        return errors;
      }
    }

    if (schema.type === "string" && typeof value === "string") {
      if (schema.minLength !== undefined && value.length < schema.minLength) {
        errors.push(`${propName}: minimum length ${schema.minLength}, got ${value.length}`);
      }

      if (schema.maxLength !== undefined && value.length > schema.maxLength) {
        errors.push(`${propName}: maximum length ${schema.maxLength}, got ${value.length}`);
      }

      if (schema.pattern) {
        try {
          const regex = new RegExp(schema.pattern);
          if (!regex.test(value)) {
            errors.push(`${propName}: does not match pattern ${schema.pattern}`);
          }
        } catch (err) {
          errors.push(`${propName}: invalid regex pattern ${schema.pattern}`);
        }
      }

      if (schema.enum && !schema.enum.includes(value)) {
        errors.push(
          `${propName}: must be one of ${schema.enum.join(", ")}, got ${value}`
        );
      }
    }

    if ((schema.type === "number" || schema.type === "integer") && typeof value === "number") {
      if (schema.type === "integer" && !Number.isInteger(value)) {
        errors.push(`${propName}: expected integer, got ${value}`);
      }

      if (schema.minimum !== undefined && value < schema.minimum) {
        errors.push(`${propName}: minimum value ${schema.minimum}, got ${value}`);
      }

      if (schema.maximum !== undefined && value > schema.maximum) {
        errors.push(`${propName}: maximum value ${schema.maximum}, got ${value}`);
      }
    }

    if (schema.type === "boolean" && typeof value === "boolean") {
      // válido, sin reglas extra
    }

    if (schema.type === "array" && Array.isArray(value)) {
      if (schema.minItems !== undefined && value.length < schema.minItems) {
        errors.push(`${propName}: minimum items ${schema.minItems}, got ${value.length}`);
      }

      if (schema.maxItems !== undefined && value.length > schema.maxItems) {
        errors.push(`${propName}: maximum items ${schema.maxItems}, got ${value.length}`);
      }

      if (schema.items) {
        value.forEach((item, index) => {
          const itemErrors = this.validateValue(
            item,
            schema.items,
            `${propName}[${index}]`
          );
          errors.push(...itemErrors);
        });
      }
    }

    if (
      schema.type === "object" &&
      value !== null &&
      typeof value === "object" &&
      !Array.isArray(value)
    ) {
      const objErrors = this.validateObject(value, schema, propName);
      errors.push(...objErrors);
    }

    return errors;
  }

  validateAndLog(message, logger = console.error) {
    const messageValidation = this.validateMessage(message);
    if (!messageValidation.valid) {
      logger("Message validation failed:", messageValidation.errors);
      return false;
    }

    const payloadValidation = this.validatePayload(message.payload, message.port);
    if (!payloadValidation.valid) {
      logger(`Payload validation failed for ${message.port}:`, payloadValidation.errors);
      return false;
    }

    return true;
  }
}

export { SchemaValidator };