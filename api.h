#ifndef SNACKOS_API_H
#define SNACKOS_API_H

#include <Arduino.h>

enum class SnackApiStatus : uint8_t {
  IDLE,
  SENDING,
  SUCCESS,
  FAILED
};

class SnackApi {
 public:
  void beginOrder(uint32_t nowMs);
  void update(uint32_t nowMs);
  void reset();

  SnackApiStatus status() const;
  bool isComplete() const;
  bool succeeded() const;
  int responseCode() const;
  const String& eta() const;
  const String& errorDetail() const;

 private:
  bool sendOrder();

  SnackApiStatus _status{SnackApiStatus::IDLE};
  uint32_t _startedAt{0};
  int _responseCode{0};
  String _eta;
  String _errorDetail;
};

#endif
