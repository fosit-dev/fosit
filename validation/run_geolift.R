# Reference harness: run Meta's GeoLift on every validation case and save its outputs as JSON.
#
#   Rscript validation/run_geolift.R validation/cases validation/out/geolift
#
# FOSIT never copies GeoLift code. GeoLift is used here only as an external
# reference implementation (see docs/METHODOLOGY.md §12). Settings mirror FOSIT's
# defaults: ridge augmentation, unit fixed effects, two-sided "Total" statistic,
# moving-block conformal inference, alpha = 0.10.

suppressPackageStartupMessages({
  library(GeoLift)
  library(jsonlite)
})

args <- commandArgs(trailingOnly = TRUE)
cases_dir <- if (length(args) >= 1) args[1] else "validation/cases"
out_dir <- if (length(args) >= 2) args[2] else "validation/out/geolift"
conformal_type <- if (length(args) >= 3) args[3] else "block"
dir.create(out_dir, recursive = TRUE, showWarnings = FALSE)

for (case_path in list.dirs(cases_dir, recursive = FALSE)) {
  case <- fromJSON(file.path(case_path, "case.json"))
  raw <- read.csv(file.path(case_path, "data.csv"), colClasses = c("character", "character", "numeric"))
  data <- GeoDataRead(raw, date_id = "date", location_id = "geo_id", Y_id = "orders", format = "yyyy-mm-dd")

  started <- Sys.time()
  gl <- GeoLift(
    Y_id = "Y", time_id = "time", location_id = "location", data = data,
    locations = case$treated,
    treatment_start_time = case$treatment_start_time,
    treatment_end_time = case$treatment_end_time,
    alpha = 0.1, model = "Ridge", fixed_effects = TRUE,
    ConfidenceIntervals = TRUE, method = "conformal", grid_size = 250,
    stat_test = "Total", conformal_type = conformal_type, ns = 1000
  )
  elapsed <- as.numeric(difftime(Sys.time(), started, units = "secs"))

  # Unrounded lift, defined exactly as GeoLift defines Perc.Lift (which it rounds to 0.1 pp)
  y_hat <- as.numeric(gl$y_hat)
  window <- case$treatment_start_time:case$treatment_end_time
  treated_rows <- which(gl$results$data$trt == 1)
  observed_avg <- colMeans(matrix(gl$results$data$y[treated_rows, ], nrow = length(treated_rows)))
  lift <- (sum(observed_avg) - sum(y_hat[window])) / abs(sum(y_hat[window]))

  out <- list(
    case = case$name,
    conformal_type = conformal_type,
    geolift_version = as.character(packageVersion("GeoLift")),
    augsynth_version = as.character(packageVersion("augsynth")),
    seconds = elapsed,
    att = gl$inference$ATT,
    att_ci = c(gl$inference$Lower.Conf.Int, gl$inference$Upper.Conf.Int),
    perc_lift_rounded = gl$inference$Perc.Lift,
    lift = lift,
    p_value = gl$inference$pvalue,
    incremental = gl$incremental,
    incremental_ci = c(gl$lower_bound, gl$upper_bound),
    lambda = if (is.null(gl$results$lambda)) NA else gl$results$lambda,
    y_hat = y_hat,
    weights = gl$df_weights
  )
  write_json(out, file.path(out_dir, paste0(case$name, ".json")), auto_unbox = TRUE, digits = NA, pretty = TRUE)
  cat(sprintf("%-12s att=%.4f p=%.3f lambda=%s (%.0fs)\n", case$name, out$att, out$p_value, format(out$lambda), elapsed))
}
