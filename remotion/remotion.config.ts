import { Config } from "@remotion/cli/config";

Config.setVideoImageFormat("jpeg");
Config.setOverwriteOutput(true);
// The cards are flat colour and type; a high CRF would show banding on
// the large areas of white.
Config.setCrf(18);
