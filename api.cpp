#include <Arduino.h>
#include <ArduinoJson.h>
#include <HTTPClient.h>
#include <WiFi.h>

#include "api.h"
#include "config.h"

void SnackApi::beginOrder(uint32_t nowMs) {
  _startedAt = nowMs;
  _responseCode = 0;
  _eta = "";
  _errorDetail = "";
  _status = SnackApiStatus::SENDING;
}

void SnackApi::update(uint32_t nowMs) {
  (void)nowMs;

  if (_status != SnackApiStatus::SENDING) {
    return;
  }

  _status = sendOrder() ? SnackApiStatus::SUCCESS : SnackApiStatus::FAILED;
}

void SnackApi::reset() {
  _status = SnackApiStatus::IDLE;
  _responseCode = 0;
  _eta = "";
  _errorDetail = "";
}

SnackApiStatus SnackApi::status() const {
  return _status;
}

bool SnackApi::isComplete() const {
  return _status == SnackApiStatus::SUCCESS ||
         _status == SnackApiStatus::FAILED;
}

bool SnackApi::succeeded() const {
  return _status == SnackApiStatus::SUCCESS;
}

int SnackApi::responseCode() const {
  return _responseCode;
}

const String& SnackApi::eta() const {
  return _eta;
}

const String& SnackApi::errorDetail() const {
  return _errorDetail;
}

bool SnackApi::sendOrder() {
  if (WiFi.status() != WL_CONNECTED) {
    _responseCode = 0;
    _errorDetail = "Wi-Fi disconnected";
    Serial.print("Connection Error: ");
    Serial.println(_errorDetail);
    return false;
  }

  JsonDocument requestDoc;
  requestDoc["device"] = SNACKOS_NAME;
  requestDoc["button"] = "pressed";

  String payload;
  serializeJson(requestDoc, payload);

  WiFiClient client;
  HTTPClient http;

  if (!http.begin(client, SERVER_URL)) {
    _responseCode = 0;
    _errorDetail = "HTTP begin failed";
    Serial.print("Connection Error: ");
    Serial.println(_errorDetail);
    return false;
  }

  http.setTimeout(API_HTTP_TIMEOUT_MS);
  http.addHeader("Content-Type", "application/json");
  _responseCode = http.POST(payload);
  Serial.print("HTTP Status: ");
  Serial.println(_responseCode);

  String response;
  if (_responseCode > 0) {
    response = http.getString();
  } else {
    _errorDetail = HTTPClient::errorToString(_responseCode);
    Serial.print("Connection Error: ");
    Serial.println(_errorDetail);
  }
  Serial.println();
  Serial.println("Response:");
  Serial.println();
  Serial.println(response);

  http.end();

  if (_responseCode != 200) {
    if (_errorDetail.length() == 0) {
      _errorDetail = String("HTTP ") + _responseCode;
    }
    return false;
  }

  JsonDocument responseDoc;
  DeserializationError error = deserializeJson(responseDoc, response);
  if (!error) {
    JsonVariantConst etaValue = responseDoc["eta"];
    if (etaValue.is<const char*>()) {
      _eta = etaValue.as<const char*>();
    } else if (!etaValue.isNull()) {
      _eta = etaValue.as<String>();
    }
  } else {
    Serial.print("[API] JSON parse warning: ");
    Serial.println(error.c_str());
  }

  if (_eta.length() == 0) {
    _eta = "Soon";
  }

  return true;
}
