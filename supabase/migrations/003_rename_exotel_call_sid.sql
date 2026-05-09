-- Rename exotel_call_sid to call_sid now that we use Twilio
ALTER TABLE calls RENAME COLUMN exotel_call_sid TO call_sid;
